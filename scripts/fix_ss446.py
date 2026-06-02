import os
import sys
from sqlalchemy.orm import Session

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database import SessionLocal
from backend.models import Bill, BankAlert, AuditLog

def fix_ss446():
    db = SessionLocal()
    try:
        bill = db.query(Bill).filter(Bill.bill_number == "SS-446").first()
        if not bill:
            print("Bill SS-446 not found.")
            return

        print(f"Current State: Total={bill.total_amount}, Bank={bill.bank_received}, Remaining={bill.remaining_amount}, Status={bill.status}")
        
        # Reset confirmed amounts and bank_received
        bill.bank_received = 1549.00
        bill.sms_confirmed_amount = 1549.00
        bill.remaining_amount = 0.0
        bill.status = "Green"
        bill.status_text = "Cleared (Manual Fix for Double-Count)"
        bill.review_required = 0
        
        # Ensure the alert is marked as reconciled
        alert = db.query(BankAlert).filter(BankAlert.utr_reference == "615334259505").first()
        if alert:
            alert.reconciled = True
            
        db.commit()
        print("Fixed SS-446 state.")
        
    finally:
        db.close()

if __name__ == "__main__":
    fix_ss446()
