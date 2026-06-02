import pytest
import re
from datetime import datetime
from backend.database import SessionLocal
from backend.models import Bill, BankAlert, Payment
from backend.reconciliation.logic import verify_payment_event
from backend.pdf_ingestion import parse_pdf
import os

def test_sg893_reconciliation_logic():
    db = SessionLocal()
    
    # 1. Mock the parser output for SG-893
    # Based on the user report and raw text analysis
    text = """
Invoice No. : SG-893 Date: 02/06/2026
MANALI J SINGH
Total 11026.00
CASH 10026.00
UPI RTGS/CHQ. 1000.00
"""
    # We'll use a unique number and unique amount to avoid collision
    unique_no = f"SG-893-TEST-{datetime.now().timestamp()}"
    unique_total = 11026.44
    unique_rem = 1000.44
    
    # Create the bill as if ingested
    bill = Bill(
        bill_number=unique_no,
        amount=unique_total,
        customer_name="MANALI J SINGH",
        invoice_date=datetime(2026, 6, 2),
        cash_received=10026.00,
        remaining_amount=unique_rem,
        status="Yellow",
        is_test_data=False # Engine filters for False
    )
    db.add(bill)
    db.commit()
    
    # Create the bank alert
    alert = BankAlert(
        bank_name="ICICI",
        amount=unique_rem,
        utr_reference=f"REF-{unique_no}",
        sender="TEST SENDER",
        received_at=datetime(2026, 6, 2, 16, 15),
        raw_text=f"ICICI credit ₹{unique_rem} Ref {unique_no}",
        reconciled=False
    )
    db.add(alert)
    db.commit()
    
    try:
        # 3. Run reconciliation
        verify_payment_event(db, alert)
        db.refresh(bill)
        
        print(f"Bill Status: {bill.status}")
        print(f"Bill Status Text: {bill.status_text}")
        print(f"Bank Rcvd: {bill.bank_received}")
        print(f"Remaining: {bill.remaining_amount}")
        
        # EXPECTATION:
        # Total Credits = 10026 (Cash) + 1000 (Bank) = 11026
        # 11026 == 11026 -> Green
        assert bill.status == "Green"
        assert "CASH_PLUS_BANK_CONFIRMED" in bill.status_text
        print("\n[SUCCESS] SG-893 Reconciliation Logic Test Passed")
        
    finally:
        db.delete(bill)
        db.delete(alert)
        db.commit()
        db.close()

if __name__ == "__main__":
    test_sg893_reconciliation_logic()
