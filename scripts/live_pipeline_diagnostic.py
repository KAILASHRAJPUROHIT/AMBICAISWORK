import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy.orm import Session

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.database import SessionLocal
from backend.models import Bill, BankAlert, SMSAlert, Payment
from backend.reconciliation.logic import is_store_open

load_dotenv()

def run_diagnostic():
    print("=== ARADHANA PAYMENT AUDITOR LIVE PIPELINE DIAGNOSTIC ===")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("-" * 50)

    # 1. IMAP Config
    imap_server = os.getenv("IMAP_SERVER") or os.getenv("IMAP_HOST") or os.getenv("BANK_IMAP_HOST")
    imap_user = os.getenv("IMAP_USER") or os.getenv("BANK_IMAP_USERNAME")
    imap_pass = os.getenv("IMAP_PASSWORD") or os.getenv("BANK_IMAP_PASSWORD")
    
    print(f"IMAP Config Loaded: {'YES' if imap_server and imap_user and imap_pass else 'NO'}")
    print(f"Monitored Mailbox: {imap_user}")
    
    # 2. Database Stats
    db = SessionLocal()
    try:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        bills_today = db.query(Bill).filter(Bill.created_at >= today_start).all()
        alerts_today = db.query(BankAlert).filter(BankAlert.created_at >= today_start).all()
        sms_alerts_today = db.query(SMSAlert).filter(SMSAlert.created_at >= today_start).all()
        
        print(f"Bills Ingested Today: {len(bills_today)}")
        print(f"Bank Alerts Today (Email): {len(alerts_today)}")
        print(f"SMS Alerts Today: {len(sms_alerts_today)}")
        
        sms_forwarder_count = len([a for a in alerts_today if "SMS Forwarded" in (a.raw_text or "")])
        bank_email_count = len(alerts_today) - sms_forwarder_count
        
        print(f"  - SMSForwarder emails: {sms_forwarder_count}")
        print(f"  - Regular Bank emails: {bank_email_count}")
        
        # 3. Reconciliation Stats
        verified = len([b for b in bills_today if b.status == "Green"])
        review_req = len([b for b in bills_today if b.review_required == 1])
        
        print(f"Verified Today: {verified}")
        print(f"Review Required Today: {review_req}")
        
        # 4. Latest Events
        print("\nLatest 10 Normalized Payment Events:")
        all_alerts = db.query(BankAlert).order_by(BankAlert.received_at.desc()).limit(10).all()
        for a in all_alerts:
            source = "SMS_FWD" if "SMS Forwarded" in (a.raw_text or "") else "EMAIL"
            print(f"[{a.received_at}] {source} | {a.bank_name} | ₹{a.amount} | Ref: {a.utr_reference} | Recon: {a.reconciled}")

        # 5. Dashboard Payload Simulation
        print("\nDashboard Metric Payload Simulation:")
        total_collection = float(sum(b.total_amount for b in bills_today) or 0.0)
        cash_confirmed = 0.0
        for b in bills_today:
            if is_store_open(b.created_at):
                cash_confirmed += float(b.cash_received or 0.0)
        
        bank_confirmed = float(sum(b.bank_received for b in bills_today) or 0.0)
        sms_confirmed = float(sum(b.sms_confirmed_amount for b in bills_today) or 0.0)
        email_confirmed = float(sum(b.email_confirmed_amount for b in bills_today) or 0.0)
        
        payload = {
            "totalBillsToday": len(bills_today),
            "verified": verified,
            "pendingReview": review_req,
            "totalCollection": total_collection,
            "cashCollection": cash_confirmed,
            "bankCollection": bank_confirmed,
            "smsConfirmed": sms_confirmed,
            "emailConfirmed": email_confirmed
        }
        for k, v in payload.items():
            print(f"  {k}: {v}")

    finally:
        db.close()

if __name__ == "__main__":
    run_diagnostic()
