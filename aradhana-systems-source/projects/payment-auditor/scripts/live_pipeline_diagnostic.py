from pathlib import Path
import sys
import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy.orm import Session

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_str = now.strftime("%Y-%m-%d")
        
        # Bills Today = invoice_date is today
        from sqlalchemy import func
        bills_today = db.query(Bill).filter(func.date(Bill.invoice_date) == today_str, Bill.is_test_data == False).all()
        
        # Imported Today = created_at >= today
        imported_today = db.query(Bill).filter(Bill.created_at >= today_start, Bill.is_test_data == False).all()
        
        alerts_today = db.query(BankAlert).filter(BankAlert.created_at >= today_start).all()
        sms_alerts_today = db.query(SMSAlert).filter(SMSAlert.created_at >= today_start).all()
        
        print(f"Bills Dated Today (Invoice Date): {len(bills_today)}")
        print(f"Bills Imported Today (Created At): {len(imported_today)}")
        print(f"Bank Alerts Today (Email): {len(alerts_today)}")
        print(f"SMS Alerts Today: {len(sms_alerts_today)}")
        
        sms_forwarder_count = len([a for a in alerts_today if "SMS Forwarded" in (a.raw_text or "")])
        bank_email_count = len(alerts_today) - sms_forwarder_count
        
        print(f"  - SMSForwarder emails: {sms_forwarder_count}")
        print(f"  - Regular Bank emails: {bank_email_count}")
        
        # 3. Reconciliation Stats
        verified_today = len([b for b in bills_today if b.status == "Green"])
        
        # Pending Previous Days = unresolved invoices where invoice_date < today
        from sqlalchemy import or_
        pending_previous = db.query(Bill).filter(
            func.date(Bill.invoice_date) < today_str,
            or_(Bill.status == "Yellow", Bill.status == "Blue", Bill.review_required == 1)
        ).count()
        
        print(f"Verified Dated Today: {verified_today}")
        print(f"Pending from Previous Days: {pending_previous}")
        
        # 4. Latest Events
        print("\nLatest 10 Normalized Payment Events:")
        all_alerts = db.query(BankAlert).order_by(BankAlert.received_at.desc()).limit(10).all()
        for a in all_alerts:
            source = "SMS_FWD" if "SMS Forwarded" in (a.raw_text or "") else "EMAIL"
            print(f"[{a.received_at}] {source} | {a.bank_name} | ₹{a.amount} | Ref: {a.utr_reference} | Recon: {a.reconciled}")

        # 5. Dashboard Payload Simulation
        print("\nDashboard Metric Payload Simulation:")
        
        # Today's Collection (Strict: only payments for bills dated today)
        bills_today_ids = [b.id for b in bills_today]
        from backend.models import Payment as PaymentModel
        payments_today = db.query(PaymentModel).filter(PaymentModel.bill_id.in_(bills_today_ids)).all()
        
        total_collection = float(sum(p.amount for p in payments_today) or 0.0)
        cash_collection = float(sum(p.amount for p in payments_today if p.mode in ["CASH", "ADVANCE", "OLD_GOLD_EXCHANGE"]) or 0.0)
        bank_collection = float(sum(p.amount for p in payments_today if p.mode in ["BANK_TRANSFER", "CARD", "UPI", "NEFT", "IMPS", "RTGS"]) or 0.0)
        
        payload = {
            "totalBillsToday": len(bills_today),
            "importedToday": len(imported_today),
            "pendingPreviousDays": pending_previous,
            "verified": verified_today,
            "totalCollection": total_collection,
            "cashCollection": cash_collection,
            "bankCollection": bank_collection
        }
        for k, v in payload.items():
            print(f"  {k}: {v}")

    finally:
        db.close()

if __name__ == "__main__":
    run_diagnostic()
