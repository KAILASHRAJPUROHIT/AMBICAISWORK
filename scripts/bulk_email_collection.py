import os
import json
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from backend.imap_collector import build_imap_config, connect_imap, fetch_labeled_emails, convert_imap_message_to_raw_email

load_dotenv()

# Configuration
IMPORT_BASE = r"C:\Aradhana\BankImports"
RAW_OUT = os.path.join(IMPORT_BASE, "bank_emails_until_yesterday_raw.json")
LOG_OUT = os.path.join(IMPORT_BASE, "email_collection.log")

os.makedirs(IMPORT_BASE, exist_ok=True)

logging.basicConfig(filename=LOG_OUT, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BANK_LABELS = [
    "BANK_ICICI", "BANK_HDFC", "BANK_SBI", "BANK_KOTAK", 
    "BANK_BOB", "BANK_PNB", "BANK_UCO"
]

def collect_historical_emails():
    logger.info("Starting Historical Bank Email Collection")
    
    # Yesterday 23:59:59 filter (offset-aware)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).replace(hour=23, minute=59, second=59)
    logger.info(f"Target Date Filter: Up to {yesterday.isoformat()}")

    all_raw_emails = []
    
    try:
        config = build_imap_config()
        mail = connect_imap(config)
        
        for label in BANK_LABELS:
            logger.info(f"Probing label: {label}")
            # Note: fetch_labeled_emails uses mail.search(None, 'ALL')
            # For this test, we fetch up to 100 per label to ensure 'all' but within practical limits
            raw_msgs = fetch_labeled_emails(mail, label, limit=100)
            
            label_count = 0
            for raw_msg in raw_msgs:
                email_obj = convert_imap_message_to_raw_email(raw_msg, label)
                if not email_obj:
                    continue
                
                # Check date - ensure both are offset-aware
                e_date = email_obj.date
                if e_date.tzinfo is None:
                    e_date = e_date.replace(tzinfo=timezone.utc)
                
                if e_date > yesterday:
                    continue
                
                entry = {
                    "message_id": email_obj.message_id,
                    "label": label,
                    "sender": email_obj.sender,
                    "subject": email_obj.subject,
                    "received_at": email_obj.date.isoformat(),
                    "raw_body": email_obj.raw_body,
                    "raw_excerpt": email_obj.raw_body[:500]
                }
                all_raw_emails.append(entry)
                label_count += 1
            
            logger.info(f"Collected {label_count} emails from {label}")

        mail.logout()

        with open(RAW_OUT, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_count": len(all_raw_emails),
                "emails": all_raw_emails
            }, f, indent=4)
            
        print(f"Success: Collected {len(all_raw_emails)} raw emails to {RAW_OUT}")
        return all_raw_emails

    except Exception as e:
        logger.exception(f"Collection failed: {e}")
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    collect_historical_emails()
