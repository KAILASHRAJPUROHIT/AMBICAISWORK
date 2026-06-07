import os
import hashlib
import logging
import json
from datetime import datetime
from sqlalchemy.orm import Session
from backend.models import BankDocument
from backend.audit_service import create_audit_log
from backend.schemas import AuditLogCreate

logger = logging.getLogger("BankDocumentIngestion")

# Local Storage Paths
BASE_STORAGE_PATH = r"C:\AradhanaAuditor\bank_documents"
INCOMING_PATH = os.path.join(BASE_STORAGE_PATH, "incoming")

def ensure_directories():
    os.makedirs(INCOMING_PATH, exist_ok=True)
    os.makedirs(os.path.join(BASE_STORAGE_PATH, "archive"), exist_ok=True)
    os.makedirs(os.path.join(BASE_STORAGE_PATH, "failed"), exist_ok=True)
    os.makedirs(os.path.join(BASE_STORAGE_PATH, "hdfc", "statements"), exist_ok=True)
    os.makedirs(os.path.join(BASE_STORAGE_PATH, "hdfc", "settlements"), exist_ok=True)
    os.makedirs(os.path.join(BASE_STORAGE_PATH, "icici", "settlements"), exist_ok=True)

def get_file_hash_from_bytes(byte_content: bytes) -> str:
    sha256_hash = hashlib.sha256()
    sha256_hash.update(byte_content)
    return sha256_hash.hexdigest()

def classify_document(sender: str, subject: str, filename: str) -> tuple[str, str, str, str]:
    combined = f"{sender} {subject} {filename}".upper()
    
    bank_name = "UNKNOWN"
    if "HDFC" in combined:
        bank_name = "HDFC"
    elif "ICICI" in combined:
        bank_name = "ICICI"

    classification = "UNKNOWN_BANK_DOCUMENT"
    classification_reason = f"Fallback. Bank: {bank_name}"
    
    if bank_name == "HDFC":
        if "STATEMENT" in combined:
            classification = "HDFC_ACCOUNT_STATEMENT"
            classification_reason = "HDFC + STATEMENT keywords"
        elif "MERCHANT" in combined or "MPR" in combined or "SETTLEMENT" in combined:
            classification = "HDFC_MERCHANT_SETTLEMENT"
            classification_reason = "HDFC + MERCHANT/MPR/SETTLEMENT keywords"
    elif bank_name == "ICICI":
        if "MERCHANT" in combined or "SETTLEMENT" in combined or "STATEMENT" in combined:
            classification = "ICICI_MERCHANT_SETTLEMENT"
            classification_reason = "ICICI + MERCHANT/SETTLEMENT/STATEMENT keywords"

    file_type = "UNKNOWN"
    fname_upper = filename.upper()
    if fname_upper.endswith(".PDF"):
        file_type = "PDF"
    elif fname_upper.endswith(".XLS"):
        file_type = "XLS"
    elif fname_upper.endswith(".XLSX"):
        file_type = "XLSX"

    return bank_name, classification, file_type, classification_reason

def process_email_attachments(db: Session, attachments: list, message_id: str, sender: str, subject: str, received_at: datetime):
    ensure_directories()
    
    for attachment in attachments:
        try:
            # Isolate transaction for each attachment
            with db.begin_nested():
                original_filename = attachment.get("filename", "unknown_attachment")
                content = attachment.get("content")
                
                if not content:
                    continue
                    
                bank_name, classification, file_type, classification_reason = classify_document(sender, subject, original_filename)
                
                # Accept only .pdf, .xls, .xlsx
                if file_type not in ["PDF", "XLS", "XLSX"]:
                    logger.info(f"Skipping attachment {original_filename} (Unsupported file type)")
                    continue
                    
                file_hash = get_file_hash_from_bytes(content)
                file_size_bytes = len(content)
                
                # Skip duplicate hashes
                existing_doc = db.query(BankDocument).filter(BankDocument.file_hash == file_hash).first()
                if existing_doc:
                    logger.info(f"Skipping duplicate attachment hash for {original_filename}")
                    continue
                    
                # Save to incoming
                safe_filename = "".join(c for c in original_filename if c.isalnum() or c in " ._-")
                timestamp_prefix = datetime.now().strftime("%Y%m%d%H%M%S")
                stored_filename = f"{timestamp_prefix}_{safe_filename}"
                file_path = os.path.join(INCOMING_PATH, stored_filename)
                
                try:
                    with open(file_path, "wb") as f:
                        f.write(content)
                except Exception as e:
                    logger.error(f"Failed to write attachment {original_filename} to disk: {e}")
                    raise e

                # Create BankDocument row
                new_doc = BankDocument(
                    bank_name=bank_name,
                    classification=classification,
                    classification_reason=classification_reason,
                    file_type=file_type,
                    original_filename=original_filename,
                    stored_filename=stored_filename,
                    file_path=file_path,
                    file_size_bytes=file_size_bytes,
                    file_hash=file_hash,
                    source_email_id=message_id,
                    sender=sender,
                    subject=subject,
                    received_at=received_at,
                    status="SAVED"
                )
                db.add(new_doc)
                db.flush()
                
                # Create audit log using standard service
                audit_payload = AuditLogCreate(
                    entity_type="BankDocument",
                    entity_id=new_doc.id,
                    action="ATTACHMENT_SAVED",
                    actor="SYSTEM",
                    metadata_json=json.dumps({"original_filename": original_filename, "file_type": file_type, "size_bytes": file_size_bytes})
                )
                create_audit_log(db, audit_payload)
                
                logger.info(f"Successfully saved and logged attachment: {original_filename}")
        except Exception as e:
            logger.error(f"Error processing attachment {attachment.get('filename', 'unknown')}: {e}")
            # The transaction for THIS attachment rolls back, but loop continues
            continue
            
    # Flush all successful attachment saves for this email
    db.flush()
