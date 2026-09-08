from pathlib import Path
import sys
import os
import logging
from datetime import datetime
from sqlalchemy.orm import Session

# Add the project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal
from backend.email_poller import process_emails, email_status, get_checkpoint
from backend.models import BankAlert, SMSAlert

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def run_once():
    print("=== Starting Email Poll Once ===")
    db = SessionLocal()
    try:
        checkpoint = get_checkpoint(db)
        print(f"Current Checkpoint: {checkpoint}")
        
        # Get counts before
        bank_alerts_before = db.query(BankAlert).count()
        sms_alerts_before = db.query(SMSAlert).count()
        
        process_emails()
        
        # Get counts after
        bank_alerts_after = db.query(BankAlert).count()
        sms_alerts_after = db.query(SMSAlert).count()
        
        print("\n=== Results ===")
        print(f"Status: {email_status}")
        print(f"Bank Alerts Found: {bank_alerts_after - bank_alerts_before}")
        print(f"SMS Alerts Found: {sms_alerts_after - sms_alerts_before}")
        print(f"Total Events Found (Status): {email_status['events_found']}")
        
        new_checkpoint = get_checkpoint(db)
        print(f"New Checkpoint: {new_checkpoint}")
        
    except Exception as e:
        print(f"Error during poll: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_once()
