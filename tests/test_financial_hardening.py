import pytest
from backend.database import SessionLocal
from backend.models import Bill, BankAlert, Payment
from backend.reconciliation.logic import verify_payment_event
from datetime import datetime

import logging
logging.basicConfig(level=logging.INFO)

def test_advance_failsafe():
    db = SessionLocal()
    # 1. Create a bill with advance
    # Use unique amount to avoid ambiguity
    unique_amt = 8000.12
    bill = Bill(
        bill_number="HARDENING-ADV-001",
        amount=10000.12,
        advance_amount=2000.0,
        remaining_amount=unique_amt,
        status="Yellow",
        is_test_data=False,
        customer_name="HARDENING ADVANCE CUSTOMER",
        invoice_date=datetime.now(),
        advance_source="MIXED" # Known but unverified
    )
    db.add(bill)
    db.commit()
    
    # 2. Create a bank alert that perfectly matches the remaining amount
    alert = BankAlert(
        bank_name="ICICI",
        amount=unique_amt,
        utr_reference="UTR-ADV-TEST",
        sender="TEST SENDER",
        received_at=datetime.now(),
        raw_text=f"Received ₹{unique_amt} from HARDENING ADVANCE CUSTOMER Ref UTR-ADV-TEST"
    )
    db.add(alert)
    db.commit()
    
    try:
        # 3. Reconcile
        verify_payment_event(db, alert)
        db.refresh(bill)
        
        # EXPECTATION: Status should be Blue/ADVANCE_REQUIRES_VERIFICATION, not Green
        assert bill.status == "Blue"
        assert "ADVANCE_REQUIRES_VERIFICATION" in bill.status_text
        print("\n[SUCCESS] Advance Failsafe Test Passed")
        
    finally:
        db.delete(bill)
        db.delete(alert)
        db.commit()
        db.close()

def test_ambiguity_failsafe():
    db = SessionLocal()
    # 1. Create 2 bills with same unique amount
    unique_amt = 5555.22
    b1 = Bill(bill_number="HARDENING-AMB-01", amount=unique_amt, status="Yellow", is_test_data=False, customer_name="CUST A", invoice_date=datetime.now())
    b2 = Bill(bill_number="HARDENING-AMB-02", amount=unique_amt, status="Yellow", is_test_data=False, customer_name="CUST B", invoice_date=datetime.now())
    db.add(b1); db.add(b2)
    db.commit()
    
    # 2. Create an alert for unique_amt without enough evidence to distinguish
    alert = BankAlert(
        bank_name="SBI", amount=unique_amt, utr_reference="UTR-AMB-TEST", 
        sender="UNKNOWN", received_at=datetime.now(), raw_text=f"Received ₹{unique_amt}"
    )
    db.add(alert); db.commit()
    
    try:
        # 3. Reconcile
        verify_payment_event(db, alert)
        db.refresh(b1); db.refresh(b2)
        
        # EXPECTATION: The best candidate (or all) should be Blue/AMBIGUOUS
        # In our code, best_bill gets the status update.
        assert b1.status == "Blue" or b2.status == "Blue"
        assert b1.status != "Green" and b2.status != "Green"
        print("[SUCCESS] Ambiguity Failsafe Test Passed")
        
    finally:
        db.delete(b1); db.delete(b2); db.delete(alert)
        db.commit(); db.close()

def test_duplicate_utr_failsafe():
    db = SessionLocal()
    # 1. Create a bill already cleared with a UTR
    b1 = Bill(bill_number="HARDENING-DUP-01", amount=1000.0, status="Green", is_test_data=False, customer_name="CUST A")
    db.add(b1); db.commit()
    p1 = Payment(bill_id=b1.id, amount=1000.0, mode="BANK_TRANSFER", status="Green", utr_reference="SAME-UTR-123")
    db.add(p1); db.commit()
    
    # 2. Create another bill with same amount
    b2 = Bill(bill_number="HARDENING-DUP-02", amount=1000.0, status="Yellow", is_test_data=False, customer_name="CUST B")
    db.add(b2); db.commit()
    
    # 3. Create an alert with the SAME UTR
    alert = BankAlert(
        bank_name="SBI", amount=1000.0, utr_reference="SAME-UTR-123", 
        sender="CUST B", received_at=datetime.now(), raw_text="Received ₹1000 from CUST B Ref SAME-UTR-123"
    )
    db.add(alert); db.commit()
    
    try:
        # 4. Reconcile
        verify_payment_event(db, alert)
        db.refresh(b2)
        
        # EXPECTATION: Status should be Red, reason DUPLICATE_UTR
        assert b2.status == "Red"
        assert "DUPLICATE_UTR" in b2.status_text
        print("[SUCCESS] Duplicate UTR Failsafe Test Passed")
        
    finally:
        db.delete(b1); db.delete(p1); db.delete(b2); db.delete(alert)
        db.commit(); db.close()

def test_unverified_advance_purple():
    db = SessionLocal()
    # 1. Create a bill with advance but NO source
    unique_amt = 7000.45
    bill = Bill(
        bill_number="HARDENING-ADV-PURPLE",
        amount=10000.45,
        advance_amount=3000.0,
        remaining_amount=unique_amt,
        status="Yellow",
        is_test_data=False,
        customer_name="PURPLE ADVANCE CUSTOMER",
        invoice_date=datetime.now(),
        advance_source=None # Crucial part
    )
    db.add(bill)
    db.commit()
    
    # 2. Create a bank alert that perfectly matches the remaining amount
    alert = BankAlert(
        bank_name="SBI",
        amount=unique_amt,
        utr_reference="UTR-ADV-PURPLE",
        sender="TEST SENDER",
        received_at=datetime.now(),
        raw_text=f"Received ₹{unique_amt} from PURPLE ADVANCE CUSTOMER Ref UTR-ADV-PURPLE"
    )
    db.add(alert)
    db.commit()
    
    try:
        # 3. Reconcile
        verify_payment_event(db, alert)
        db.refresh(bill)
        
        # EXPECTATION: Status should be Purple, reason ADVANCE_PAYMENT_TYPE_UNKNOWN
        assert bill.status == "Purple"
        assert bill.status_text == "ADVANCE_PAYMENT_TYPE_UNKNOWN"
        print("[SUCCESS] Unverified Advance Purple Test Passed")
        
    finally:
        db.delete(bill)
        db.delete(alert)
        db.commit()
        db.close()

if __name__ == "__main__":
    test_advance_failsafe()
    test_ambiguity_failsafe()
    test_duplicate_utr_failsafe()
    test_unverified_advance_purple()
