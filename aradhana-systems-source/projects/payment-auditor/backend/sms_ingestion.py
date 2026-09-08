import time
import logging
from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models import SMSAlert, Bill, AuditLog, BankAlert
from backend.reconciliation_orchestrator_v2 import reconcile_bank_payments
import json
import re

logger = logging.getLogger("SMS_Ingestion")

def poll_android_sms():
    """
    Simulation of Android SMS collection.
    In production, this would call a local Android-gateway API or read from a shared file.
    """
    logger.info("Polling Android SMS via local route...")
    
    # Mock data - simulate finding a bank SMS
    mock_sms = [
        {
            "phone": "+919876543210",
            "body": "Your A/c XX123 is credited with INR 5,000.00 on 01-Jun-26. Info: UPI/612345678901/PAYER NAME/HDFC.",
            "timestamp": "2026-06-01T10:00:00"
        }
    ]
    
    db = SessionLocal()
    try:
        for sms in mock_sms:
            # Extract amount
            amt_match = re.search(r"INR\s*([\d,]+\.\d{2})", sms["body"])
            amount = float(amt_match.group(1).replace(",", "")) if amt_match else 0.0
            
            # Extract UTR
            utr_match = re.search(r"UPI/(\d{12})", sms["body"])
            utr = utr_match.group(1) if utr_match else None
            
            # Check for existing
            exists = db.query(SMSAlert).filter(SMSAlert.utr_reference == utr).first()
            if not exists and utr:
                new_sms = SMSAlert(
                    phone_source=sms["phone"],
                    amount=amount,
                    utr_reference=utr,
                    received_at=datetime.fromisoformat(sms["timestamp"]),
                    raw_text=sms["body"]
                )
                db.add(new_sms)
                
                # Also add as a BankAlert for the reconciliation engine to pick up
                new_alert = BankAlert(
                    bank_name="SMS_GATEWAY",
                    amount=amount,
                    utr_reference=utr,
                    sender="SMS_GATEWAY",
                    received_at=datetime.fromisoformat(sms["timestamp"]),
                    raw_text=f"SMS: {sms['body']}"
                )
                db.add(new_alert)
                
                logger.info(f"Ingested SMS Bank Alert: {utr}")
                
        db.commit()
        # Trigger reconciliation
        reconcile_bank_payments()
        
    except Exception as e:
        db.rollback()
        logger.error(f"SMS Ingestion Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    while True:
        poll_android_sms()
        time.sleep(1800) # 30 minutes
