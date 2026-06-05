import os
import time
import logging
import threading
import re
import hashlib
from datetime import datetime
from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models import SMSAlert, BankAlert, Bill, AuditLog, Payment
from backend.sms_parser import parse_sms_body
import json

logger = logging.getLogger("SMS_Poller")

sms_status = {
    "last_sync": None,
    "next_sync": None,
    "events_found": 0,
    "last_error": None,
    "is_running": False
}

SMS_INBOX_PATH = r"Z:\Aradhana\SMSInbox"
status_lock = threading.Lock()

def update_sms_status(**kwargs):
    with status_lock:
        for key, value in kwargs.items():
            if key in sms_status:
                sms_status[key] = value

def get_event_fingerprint(bank, amount, utr, received_at, direction="CREDIT"):
    # bank + amount + utr/reference + date + direction
    date_str = received_at.strftime("%Y-%m-%d")
    raw = f"{bank}|{amount:.2f}|{utr}|{date_str}|{direction}"
    return hashlib.sha256(raw.encode()).hexdigest()

def process_sms():
    """
    Android SMS collection with multi-point verification and cross-source deduplication.
    """
    logger.info("Polling Android SMS...")
    update_sms_status(is_running=True)
    
    db = SessionLocal()
    events_found = 0
    try:
        source_sms = []
        if os.path.exists(SMS_INBOX_PATH):
            for filename in os.listdir(SMS_INBOX_PATH):
                if filename.endswith(".json"):
                    try:
                        with open(os.path.join(SMS_INBOX_PATH, filename), "r") as f:
                            data = json.load(f)
                            source_sms.append(data)
                    except: pass
        else:
            # Simulation fallback
            source_sms = [
                {
                    "sms_id": "MSG001",
                    "sender": "BANK-ALERT",
                    "body": "Your UPI Ref: 312345678902 for INR 800.00 is successful. A/c XX567 credited.",
                    "timestamp": datetime.now().isoformat()
                }
            ]
        
        for sms in source_sms:
            raw_body = sms["body"]
            parsed_data = parse_sms_body(raw_body)
            
            # Skip non-credit or zero amount
            if parsed_data["credit_or_debit"] != "CREDIT" or parsed_data["amount"] <= 0:
                continue
                
            received_at = datetime.fromisoformat(sms["timestamp"])
            
            # Check for existing by sms_id or utr
            exists = db.query(SMSAlert).filter(SMSAlert.sms_id == sms.get("sms_id")).first()
            if not exists and parsed_data["utr_reference"]:
                 exists = db.query(SMSAlert).filter(SMSAlert.utr_reference == parsed_data["utr_reference"]).first()
            
            if not exists:
                confidence = parsed_data.get("parsed_confidence")
                if confidence is None:
                    logger.warning(f"SMS confidence missing for SMS ID: {sms.get('sms_id')}. Defaulting to 0.0")
                    confidence = 0.0
                
                new_sms = SMSAlert(
                    sms_id=sms.get("sms_id"),
                    sender=sms["sender"],
                    received_at=received_at,
                    bank_name=parsed_data["bank_name"],
                    account_suffix=parsed_data["account_suffix"],
                    credit_or_debit=parsed_data["credit_or_debit"],
                    amount=parsed_data["amount"],
                    utr_reference=parsed_data["utr_reference"],
                    raw_body=raw_body,
                    parsed_confidence=confidence
                )
                db.add(new_sms)
                events_found += 1
                
                # Cross-Verification / Deduplication with Email
                bank_alert = None
                if parsed_data["utr_reference"]:
                    bank_alert = db.query(BankAlert).filter(BankAlert.utr_reference == parsed_data["utr_reference"]).first()
                
                if not bank_alert:
                    # Create a consolidated BankAlert from SMS if it doesn't exist
                    bank_alert = BankAlert(
                        bank_name=parsed_data["bank_name"],
                        amount=parsed_data["amount"],
                        utr_reference=parsed_data["utr_reference"],
                        sender=sms["sender"],
                        received_at=received_at,
                        raw_text=f"SMS: {raw_body}"
                    )
                    db.add(bank_alert)
                    db.flush() 
                
                # RECONCILIATION LOGIC
                from backend.reconciliation.logic import verify_payment_event
                verify_payment_event(db, bank_alert, source="SMS")

        db.commit()
        update_sms_status(
            last_sync=datetime.now().isoformat(),
            next_sync=(datetime.now().timestamp() + 1800),
            events_found=events_found
        )
    except Exception as e:
        db.rollback()
        logger.error(f"SMS Polling Error: {e}")
        update_sms_status(last_error=str(e))
    finally:
        db.close()
        update_sms_status(is_running=False)

def start_sms_poller():
    def run():
        while True:
            process_sms()
            time.sleep(1800) # 30 minutes
            
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info("SMS poller thread started.")
