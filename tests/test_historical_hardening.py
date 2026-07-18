import pytest
from backend.database import SessionLocal
from backend.models import Bill, BankAlert, Payment
from backend.reconciliation.logic import verify_payment_event
from datetime import datetime, timedelta

def test_historical_payment_purple():
    db = SessionLocal()
    # 1. Create a bill dated June 2nd
    inv_date = datetime(2026, 6, 2)
    unique_no = f"HARDENING-HIST-{datetime.now().timestamp()}"
    unique_amt = 9999.88
    bill = Bill(
        bill_number=unique_no,
        amount=unique_amt,
        status="Yellow",
        is_test_data=False,
        customer_name="HISTORICAL CUSTOMER",
        invoice_date=inv_date
    )
    db.add(bill)
    db.commit()
    
    # 2. Create a payment record for this bill with a PAST date (June 1st)
    pay_date = datetime(2026, 6, 1)
    payment = Payment(
        bill_id=bill.id,
        amount=unique_amt,
        mode="BANK_TRANSFER",
        payment_date=pay_date,
        status="Yellow"
    )
    db.add(payment)
    db.commit()
    
    # 3. Create a bank alert that perfectly matches
    alert = BankAlert(
        bank_name="HDFC",
        amount=unique_amt,
        utr_reference="UTR-HIST-TEST-UNIQUE",
        sender="TEST SENDER",
        received_at=pay_date,
        raw_text=f"Received ₹{unique_amt} from HISTORICAL CUSTOMER Ref UTR-HIST-TEST-UNIQUE"
    )
    db.add(alert)
    db.commit()
    
    try:
        # 4. Reconcile
        verify_payment_event(db, alert)
        db.refresh(bill)
        
        print(f"Bill Status: {bill.status}")
        print(f"Bill Status Text: {bill.status_text}")
        
        # EXPECTATION: Status should be Purple, reason HISTORICAL_PAYMENT_VERIFICATION
        assert bill.status == "Purple"
        assert "HISTORICAL_PAYMENT_VERIFICATION" in bill.status_text
        print("\n[SUCCESS] Historical Payment Purple Test Passed")
        
        # 5. Test High Value Escalation (₹50,000)
        bill.amount = 60000.0
        payment.amount = 60000.0
        alert.amount = 60000.0
        alert.reconciled = False # Reset for retry
        db.commit()
        
        verify_payment_event(db, alert)
        db.refresh(bill)
        assert "HIGH_VALUE_ESCALATION" in bill.status_text
        print("[SUCCESS] High Value Historical Escalation Test Passed")

    finally:
        db.delete(bill)
        db.delete(payment)
        db.delete(alert)
        db.commit()
        db.close()

if __name__ == "__main__":
    test_historical_payment_purple()
