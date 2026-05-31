import os
import json
import logging
from datetime import datetime
from backend.email_ingestion.email_parser import EmailParser
from backend.email_ingestion.email_normalizer import EmailNormalizer
from backend.email_ingestion.email_validator import EmailValidator

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
JSON_OUT = os.path.join(EXPORT_BASE, "JSON", "parsed_transactions.json")
AUDIT_LOG_DIR = r"C:\Aradhana\AuditLogs"
LOG_OUT = os.path.join(EXPORT_BASE, "Logs", "email_ingestion.log")

os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
os.makedirs(AUDIT_LOG_DIR, exist_ok=True)

logging.basicConfig(filename=LOG_OUT, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Sample ICICI Emails
ICICI_SAMPLES = [
    "Your A/c XX123 is credited with INR 5,000.00 on 31-May-26. Info: UPI/312345678901/John Doe/ICICI/REF123.",
    "Dear Customer, your account XX456 has been credited with Rs. 12,500.00 on 30-May-2026. Info: INF/NEFT/N12345678/ARADHANA TRADERS.",
    "ICICI Bank Alert: Transaction of INR 500.00 on 29/05/2026. Info: INF/IMPS/654321098/Jane Smith/POS.",
    "Invalid email sample for testing validation."
]

def run_ingestion_mvp():
    logger.info("Starting Bank Email Ingestion MVP")
    
    parser = EmailParser()
    normalizer = EmailNormalizer()
    validator = EmailValidator()
    
    processed_transactions = []
    
    for raw in ICICI_SAMPLES:
        # 1. Parse
        parsed = parser.parse(raw)
        
        # 2. Normalize
        normalized = normalizer.normalize(parsed)
        
        # 3. Validate
        is_valid, errors = validator.validate(normalized)
        
        result_entry = {
            "data": normalized,
            "is_valid": is_valid,
            "errors": errors,
            "ingestion_timestamp": datetime.now().isoformat()
        }
        
        # 4. Audit Log (Immutable Event)
        log_filename = f"EMAIL_INGEST_{normalized['transaction_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        log_path = os.path.join(AUDIT_LOG_DIR, log_filename)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(result_entry, f, indent=4)
            
        if is_valid:
            processed_transactions.append(normalized)
            logger.info(f"Successfully ingested: {normalized['transaction_id']}")
        else:
            logger.warning(f"Ingestion partial/failed: {normalized['transaction_id']} - Sent to review queue.")

    # 5. Output Latest Results
    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "count": len(processed_transactions),
            "transactions": processed_transactions
        }, f, indent=4)
        
    print(f"Ingestion complete. {len(processed_transactions)} transactions saved to {JSON_OUT}")
    return processed_transactions

if __name__ == "__main__":
    run_ingestion_mvp()
