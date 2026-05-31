import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from backend.email_ingestion.email_parser import EmailParser
from backend.email_ingestion.email_normalizer import EmailNormalizer
from backend.email_ingestion.email_validator import EmailValidator
from backend.imap_collector import build_imap_config, connect_imap, fetch_labeled_emails, convert_imap_message_to_raw_email

load_dotenv()

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
JSON_OUT = os.path.join(EXPORT_BASE, "JSON", "parsed_transactions.json")
AUDIT_LOG_DIR = r"C:\Aradhana\AuditLogs"
LOG_OUT = os.path.join(EXPORT_BASE, "Logs", "email_ingestion.log")

os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
os.makedirs(AUDIT_LOG_DIR, exist_ok=True)

logging.basicConfig(filename=LOG_OUT, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def run_ingestion_mvp():
    logger.info("Starting Bank Email Ingestion (Real IMAP)")
    
    parser = EmailParser()
    normalizer = EmailNormalizer()
    validator = EmailValidator()
    
    processed_transactions = []
    
    try:
        # 1. Connect to IMAP
        config = build_imap_config()
        mail = connect_imap(config)
        
        # 2. Fetch Latest 20 from BANK_ICICI
        logger.info("Fetching latest 20 emails from BANK_ICICI label")
        raw_msgs = fetch_labeled_emails(mail, "BANK_ICICI", limit=20)
        
        for raw_msg in raw_msgs:
            email_obj = convert_imap_message_to_raw_email(raw_msg, "BANK_ICICI")
            if not email_obj:
                continue
                
            raw_text = f"{email_obj.subject}\n{email_obj.raw_body}"
            
            # 3. Parse
            parsed = parser.parse(raw_text)
            
            # 4. Normalize
            normalized = normalizer.normalize(parsed)
            
            # 5. Validate
            is_valid, errors = validator.validate(normalized)
            
            result_entry = {
                "data": normalized,
                "is_valid": is_valid,
                "errors": errors,
                "ingestion_timestamp": datetime.now().isoformat(),
                "message_id": email_obj.message_id
            }
            
            # 6. Audit Log
            log_filename = f"EMAIL_INGEST_{normalized['transaction_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
            log_path = os.path.join(AUDIT_LOG_DIR, log_filename)
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(result_entry, f, indent=4)
                
            if is_valid:
                processed_transactions.append(normalized)
                logger.info(f"Successfully ingested: {normalized['transaction_id']}")
            else:
                logger.warning(f"Ingestion partial/failed: {normalized['transaction_id']} - {errors}")

        mail.logout()

    except Exception as e:
        logger.exception(f"Critical error during IMAP ingestion: {e}")
        print(f"Error: {e}")

    # 7. Output Latest Results
    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "source": "GMAIL_IMAP",
            "mailbox": os.getenv("IMAP_USER"),
            "label": "BANK_ICICI",
            "count": len(processed_transactions),
            "transactions": processed_transactions
        }, f, indent=4)
        
    print(f"Ingestion complete. {len(processed_transactions)} transactions saved to {JSON_OUT}")
    return processed_transactions

if __name__ == "__main__":
    run_ingestion_mvp()
