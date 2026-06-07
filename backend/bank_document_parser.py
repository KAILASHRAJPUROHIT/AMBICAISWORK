import os
import logging
import json
from sqlalchemy.orm import Session
from backend.models import BankDocument, BankDocumentTransaction
from backend.audit_service import create_audit_log
from backend.schemas import AuditLogCreate

logger = logging.getLogger("BankDocumentParser")

class NeedsPasswordException(Exception):
    pass

def _parse_pdf(file_path: str) -> list:
    import pypdf
    # 1. Attempt to open. If encrypted, raise a specific NeedsPasswordException
    # 2. Extract text line by line
    # 3. Store raw lines as 'raw_text' with no structural mapping yet
    # 4. Return list of dictionaries: [{"raw_text": line, "amount": None, ...}]
    return []

def _parse_xlsx(file_path: str) -> list:
    import openpyxl
    # 1. Load workbook (data_only=True)
    # 2. Iterate rows in active sheet
    # 3. Store raw row data as 'raw_text' (JSON stringified) and map structural fields
    # 4. Return list of dictionaries with mapped fields
    return []

def parse_document(db: Session, document_id: int) -> bool:
    """
    Manually triggered parser for an existing BankDocument.
    Never auto-matches payments or triggers reconciliation.
    """
    doc = db.query(BankDocument).filter(BankDocument.id == document_id).first()
    if not doc:
        logger.error(f"Document {document_id} not found.")
        return False
        
    # Safety Check: Prevent re-parsing to avoid duplicate transaction rows
    existing_rows_count = db.query(BankDocumentTransaction).filter(BankDocumentTransaction.document_id == document_id).count()
    if existing_rows_count > 0:
        doc.status = "FAILED"
        doc.error_message = "Document already has extracted rows; reparse blocked."
        audit_payload = AuditLogCreate(
            entity_type="BankDocument",
            entity_id=doc.id,
            action="DOCUMENT_REPARSE_BLOCKED",
            actor="SYSTEM",
            metadata_json=json.dumps({"existing_rows": existing_rows_count})
        )
        create_audit_log(db, audit_payload)
        db.commit()
        return False

    if doc.file_type == "XLS":
        doc.status = "UNSUPPORTED_FORMAT"
        doc.error_message = "Legacy .xls format is not supported yet."
        audit_payload = AuditLogCreate(
            entity_type="BankDocument",
            entity_id=doc.id,
            action="DOCUMENT_UNSUPPORTED_FORMAT",
            actor="SYSTEM",
            metadata_json=json.dumps({"file_type": "XLS"})
        )
        create_audit_log(db, audit_payload)
        db.commit()
        return False

    extracted_rows = []
    new_status = "FAILED"
    
    try:
        if doc.file_type == "PDF":
            extracted_rows = _parse_pdf(doc.file_path)
            new_status = "TEXT_EXTRACTED"
        elif doc.file_type == "XLSX":
            extracted_rows = _parse_xlsx(doc.file_path)
            new_status = "PARSED"
        else:
            raise ValueError(f"Cannot parse file type: {doc.file_type}")
            
        # Insert BankDocumentTransaction rows
        for idx, row in enumerate(extracted_rows):
            txn = BankDocumentTransaction(
                document_id=doc.id,
                transaction_date=row.get("date"),
                description=row.get("description"),
                amount=row.get("amount"),
                dr_cr=row.get("dr_cr"),
                balance=row.get("balance"),
                reference_number=row.get("reference"),
                line_number=idx,
                raw_text=row.get("raw_text")
            )
            db.add(txn)
            
        doc.status = new_status
        
        # Log success before commit
        audit_payload = AuditLogCreate(
            entity_type="BankDocument",
            entity_id=doc.id,
            action=f"DOCUMENT_{new_status}",
            actor="SYSTEM",
            metadata_json=json.dumps({"rows_extracted": len(extracted_rows)})
        )
        create_audit_log(db, audit_payload)
        
        db.commit()
        return True
        
    except NeedsPasswordException:
        logger.warning(f"Document {document_id} requires a password.")
        doc.status = "NEEDS_PASSWORD"
        audit_payload = AuditLogCreate(
            entity_type="BankDocument",
            entity_id=doc.id,
            action="DOCUMENT_NEEDS_PASSWORD",
            actor="SYSTEM",
            metadata_json=json.dumps({})
        )
        create_audit_log(db, audit_payload)
        db.commit()
        return False
        
    except Exception as e:
        logger.error(f"Failed to parse document {document_id}: {e}")
        doc.status = "FAILED"
        doc.error_message = str(e)
        audit_payload = AuditLogCreate(
            entity_type="BankDocument",
            entity_id=doc.id,
            action="DOCUMENT_FAILED",
            actor="SYSTEM",
            metadata_json=json.dumps({"error": str(e)})
        )
        create_audit_log(db, audit_payload)
        db.commit()
        return False
