import os
import sys
import email
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("python-dotenv not installed, relying on existing environment variables.")

from backend.database import SessionLocal
from backend.imap_collector import build_imap_config, connect_imap, fetch_labeled_emails, decode_mime_header
from backend.bank_document_ingestion import process_email_attachments
from backend.models import BankDocument
from email.utils import parsedate_to_datetime

def run_historical_fetch():
    print(f"[{datetime.now()}] Starting Historical Bank Sample Fetch...")
    
    # Optional label from command line, default to INBOX
    labels = sys.argv[1:] if len(sys.argv) > 1 else ["INBOX"]
    
    db = SessionLocal()
    try:
        config = build_imap_config()
        print("Connecting to IMAP account: configured user redacted...")
        mail = connect_imap(config)
        
        stats = {
            "emails_scanned": 0,
            "attachments_found": 0,
            "documents_saved_estimated": 0,
            "duplicates_or_existing_estimated": 0,
            "errors": 0
        }
        
        # Count existing docs to calculate the diff safely
        docs_before = db.query(BankDocument).count()
        
        for label in labels:
            print(f"Fetching last 10 emails from label: '{label}' (Read-Only)...")
            raw_msgs = fetch_labeled_emails(mail, label, limit=10)
            
            for raw_msg in raw_msgs:
                stats["emails_scanned"] += 1
                try:
                    msg = email.message_from_bytes(raw_msg)
                    
                    message_id = msg.get('Message-ID', 'unknown')
                    sender = decode_mime_header(msg.get('From', ''))
                    subject = decode_mime_header(msg.get('Subject', ''))
                    date_str = msg.get('Date', '')
                    
                    try:
                        received_at = parsedate_to_datetime(date_str)
                    except Exception:
                        received_at = datetime.utcnow()
                    
                    attachments = []
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_disposition = str(part.get('Content-Disposition', ''))
                            if 'attachment' in content_disposition:
                                filename = part.get_filename()
                                if filename:
                                    filename = decode_mime_header(filename)
                                    fname_lower = filename.lower()
                                    if fname_lower.endswith('.pdf') or fname_lower.endswith('.xlsx') or fname_lower.endswith('.xls'):
                                        payload = part.get_payload(decode=True)
                                        if payload:
                                            attachments.append({
                                                "filename": filename,
                                                "content": payload
                                            })
                                            stats["attachments_found"] += 1
                    
                    if attachments:
                        print(f"Found {len(attachments)} target attachments in email: {subject}")
                        try:
                            # Use existing ingestion logic (which handles hashing, duplicates, and audit logs)
                            # This does NOT update checkpoints, create BankAlerts, or mark emails read
                            process_email_attachments(db, attachments, message_id, sender, subject, received_at)
                            # Ensure the outer session commits any flushed models from ingestion
                            db.commit() 
                        except Exception as e:
                            print(f"Error processing attachments for email {message_id}: {e}")
                            stats["errors"] += 1
                            db.rollback()
                            
                except Exception as e:
                    print(f"Error parsing raw message: {e}")
                    stats["errors"] += 1

        docs_after = db.query(BankDocument).count()
        docs_saved = docs_after - docs_before
        
        stats["documents_saved_estimated"] = docs_saved
        stats["duplicates_or_existing_estimated"] = stats["attachments_found"] - docs_saved
        
        mail.logout()
        
        print("\n--- Summary ---")
        for key, value in stats.items():
            print(f"{key:<35}: {value}")
            
    except Exception as e:
        print(f"\nERROR: Historical fetch failed: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    run_historical_fetch()
