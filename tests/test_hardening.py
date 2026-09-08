import pytest
from datetime import datetime, time
from backend.reconciliation.logic import is_store_open, verify_payment_event
from backend.models import Bill, Payment, BankAlert
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base

# Setup In-memory DB for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

def test_store_hours():
    # Monday 9:00 AM (Closed)
    dt_mon_closed = datetime(2026, 6, 1, 9, 0) # 2026-06-01 is Monday
    assert is_store_open(dt_mon_closed) == False
    
    # Monday 11:00 AM (Open)
    dt_mon_open = datetime(2026, 6, 1, 11, 0)
    assert is_store_open(dt_mon_open) == True
    
    # Thursday 10:00 AM (Closed)
    dt_thu_closed = datetime(2026, 6, 4, 10, 0) # 2026-06-04 is Thursday
    assert is_store_open(dt_thu_closed) == False
    
    # Thursday 1:00 PM (Open)
    dt_thu_open = datetime(2026, 6, 4, 13, 0)
    assert is_store_open(dt_thu_open) == True
    
    # Sunday 8:00 PM (Open)
    dt_sun_open = datetime(2026, 6, 7, 20, 0)
    assert is_store_open(dt_sun_open) == True

def test_partial_cash_payment(db):
    bill = Bill(
        bill_number="SS-TEST-01",
        customer_name="JOHN DOE",
        total_amount=5000.00,
        status="Yellow",
        cash_received=2000.00,
        remaining_amount=3000.00,
        reference_no="UTR123", # Set UTR to match
        created_at=datetime.now()
    )
    db.add(bill)
    db.commit()
    
    alert = BankAlert(
        bank_name="HDFC",
        amount=3000.00,
        utr_reference="UTR123",
        sender="ALERTS",
        received_at=datetime.now(),
        raw_text="Your account credited with 3000.00 Ref UTR123"
    )
    db.add(alert)
    db.flush()
    
    verify_payment_event(db, alert, source="EMAIL")
    db.refresh(bill)
    
    # It should match by UTR, score 100.
    # Total received = 2000 (cash) + 3000 (bank) = 5000.
    # So it should actually be Green!
    assert bill.status == "Green"
    assert bill.remaining_amount == 0

def test_same_amount_two_invoices(db):
    bill1 = Bill(bill_number="B1", total_amount=1000.00, status="Yellow", customer_name="ALICE", created_at=datetime.now())
    bill2 = Bill(bill_number="B2", total_amount=1000.00, status="Yellow", customer_name="BOB", created_at=datetime.now())
    db.add(bill1)
    db.add(bill2)
    db.commit()
    
    alert = BankAlert(
        bank_name="SBI",
        amount=1000.00,
        utr_reference="UTR_SAME",
        sender="ALERTS",
        received_at=datetime.now(),
        raw_text="Credited 1000.00 from ALICE"
    )
    db.add(alert)
    db.flush()
    
    verify_payment_event(db, alert, source="EMAIL")
    db.refresh(bill1)
    db.refresh(bill2)
    
    # bill1 has name match (ALICE), so it should have higher score.
    # But wait, my logic flags as Ambiguous if multiple candidates exist and score < 100.
    assert bill1.status == "Blue" # Flagged for review
    # status_text now carries the structured reason code, e.g.
    # "Review Required: AMBIGUOUS_AMOUNT_MATCH (Score: 50)"
    assert "AMBIGUOUS" in bill1.status_text.upper()

def test_sms_forwarder_parse():
    from backend.sms_parser import parse_bank_sms
    body = """From : JX-ICICIT-S()

Your ICICI Bank Account 0228 has been credited with Rs 1.00 on
2026-06-01 at 20:27:43 from KULDEEPSINGHKESHARSI.
Ref No 202741291496."""
    parsed = parse_bank_sms(body)
    assert parsed.amount == 1.00
    assert parsed.sender_bank == "ICICI"
    assert parsed.utr_reference == "202741291496"
    assert parsed.account_suffix == "0228"
    assert parsed.payer_name == "KULDEEPSINGHKESHARSI"
    assert parsed.confidence == "HIGH"

def test_sms_email_dedupe(db):
    from backend.reconciliation.logic import verify_payment_event
    from backend.models import BankAlert
    
    now = datetime.now()
    bill = Bill(bill_number="B-DUP", customer_name="KULDEEP", total_amount=1.00, status="Yellow", created_at=now, invoice_date=now)
    db.add(bill)
    db.commit()
    
    # 1. SMS arrives - Name match + Date match = 50 + 30 = 80.
    alert_sms = BankAlert(
        bank_name="ICICI", amount=1.00, utr_reference="202741291496", 
        sender="JX-ICICIT-S", received_at=now,
        raw_text="SMS: Your account credited 1.00 from KULDEEP Ref 202741291496"
    )
    db.add(alert_sms)
    db.flush()
    verify_payment_event(db, alert_sms, source="SMS")
    
    db.refresh(bill)
    assert bill.status == "Green"
    assert float(bill.bank_received) == 1.00

def test_cust_purc_reconciliation(db):
    now = datetime.now()
    # Bill for 10,000. Customer gives 2,000 worth of old gold.
    bill = Bill(
        bill_number="B-GOLD", customer_name="BOB", total_amount=10000.00, 
        cash_received=2000.00, bank_received=0, card_received=0,
        remaining_amount=8000.00, status="Yellow", created_at=now, invoice_date=now
    )
    db.add(bill)
    db.commit()
    
    # Now a bank transfer for 8,000 arrives
    alert = BankAlert(
        bank_name="HDFC", amount=8000.00, utr_reference="UTR_GOLD", 
        sender="ALERTS", received_at=now,
        raw_text="Bob paid 8000"
    )
    db.add(alert)
    db.flush()
    
    from backend.reconciliation.logic import verify_payment_event
    verify_payment_event(db, alert, source="EMAIL")
    db.refresh(bill)
    
    # It should match if name token matches (Bob) + date proximity
    assert bill.status == "Green"
    assert bill.remaining_amount == 0

from datetime import datetime, time, timedelta

def test_duplicate_notification_sms_email(db):
    now = datetime.now()
    bill = Bill(bill_number="B4", total_amount=2000.00, status="Yellow", customer_name="DAVE", invoice_date=now, created_at=now)
    db.add(bill)
    db.commit()
    
    # 1. Email arrives - name match + date proximity should be enough (50+30=80)
    alert1 = BankAlert(bank_name="SBI", amount=2000.00, utr_reference="UTR_DUP", sender="ALERTS", received_at=now, raw_text="Payment from DAVE 2000.00 Ref UTR_DUP")
    db.add(alert1)
    db.flush()
    verify_payment_event(db, alert1, source="EMAIL")
    db.refresh(bill)
    assert bill.status == "Green"
    
    # 2. SMS arrives with same UTR
    # In my logic, process_sms would check if BankAlert exists with same UTR.
    # Let's simulate that logic from sms_poller.py
    exists = db.query(BankAlert).filter(BankAlert.utr_reference == "UTR_DUP").first()
    assert exists is not None
    
    # It should not add to bank_received twice.
    old_bank_received = float(bill.bank_received)
    verify_payment_event(db, exists, source="SMS")
    db.refresh(bill)
    assert float(bill.bank_received) == old_bank_received # Should stay 2000, not 4000

def test_wrong_date_match(db):
    # Invoice is 10 days ago
    old_date = datetime.now() - timedelta(days=10)
    bill = Bill(bill_number="B5", total_amount=300.00, status="Yellow", customer_name="EVE", invoice_date=old_date, created_at=datetime.now())
    db.add(bill)
    db.commit()
    
    # Payment arrives today
    alert = BankAlert(bank_name="SBI", amount=300.00, utr_reference="UTR_OLD", sender="ALERTS", received_at=datetime.now(), raw_text="Eve 300.00 UTR_OLD")
    db.add(alert)
    db.flush()
    
    verify_payment_event(db, alert, source="EMAIL")
    db.refresh(bill)
    
    # Score should be low because of date diff (10 days)
    # Score = 0 (UTR mismatch) + 50 (Name) + 0 (Date) + 0 (Bank) = 50.
    # Should be Blue (Review Required)
    assert bill.status == "Blue"
    # status_text now carries the structured reason code, e.g.
    # "Review Required: LOW_CONFIDENCE_MATCH (Score: 50)"
    assert "LOW_CONFIDENCE" in bill.status_text.upper()
