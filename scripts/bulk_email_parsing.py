import os
import json
import logging
from datetime import datetime
from backend.email_ingestion.icici_template_parser import ICICITemplateParser

# Configuration
IMPORT_BASE = r"C:\Aradhana\BankImports"
RAW_EMAILS = os.path.join(IMPORT_BASE, "bank_emails_until_yesterday_raw.json")
PAYMENTS_OUT = os.path.join(IMPORT_BASE, "bank_payments_until_yesterday.json")
FAILURES_OUT = os.path.join(IMPORT_BASE, "bank_email_parse_failures.json")
NON_FIN_OUT = os.path.join(IMPORT_BASE, "bank_email_non_financial.json")
LOG_OUT = os.path.join(IMPORT_BASE, "bank_email_parsing.log")

logging.basicConfig(filename=LOG_OUT, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def parse_all_emails():
    logger.info("Starting Bank Email Parsing Phase")
    
    if not os.path.exists(RAW_EMAILS):
        print("Raw emails file not found.")
        return

    with open(RAW_EMAILS, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    
    emails = raw_data.get("emails", [])
    parser = ICICITemplateParser()
    
    parsed_payments = []
    non_financial = []
    failures = []
    
    for entry in emails:
        try:
            # For now, we use ICICITemplateParser as the base since we have it. 
            # In a full system, we'd have a factory for different banks.
            res = parser.parse(entry["subject"], entry["raw_body"])
            res["message_id"] = entry["message_id"]
            res["received_at"] = entry["received_at"]
            res["label"] = entry["label"]
            
            # Classification
            if res.get("is_transaction"):
                if res.get("status") == "GREEN":
                    parsed_payments.append(res)
                else:
                    failures.append(res) # Needs review
            elif res.get("status") in ["NON_FINANCIAL_ALERT", "SECURITY_ALERT"]:
                non_financial.append(res)
            else:
                failures.append(res)
                
        except Exception as e:
            logger.error(f"Error parsing email {entry['message_id']}: {e}")
            failures.append({"message_id": entry["message_id"], "error": str(e), "entry": entry})

    # Save outputs
    with open(PAYMENTS_OUT, "w", encoding="utf-8") as f:
        json.dump(parsed_payments, f, indent=4)
    with open(FAILURES_OUT, "w", encoding="utf-8") as f:
        json.dump(failures, f, indent=4)
    with open(NON_FIN_OUT, "w", encoding="utf-8") as f:
        json.dump(non_financial, f, indent=4)

    print(f"Parsing complete: {len(parsed_payments)} payments, {len(non_financial)} non-financial, {len(failures)} failures.")
    return parsed_payments

if __name__ == "__main__":
    parse_all_emails()
