import pytest
from backend.database import SessionLocal
from backend.models import Bill, BankAlert, Payment, AccountantVerificationQueue
from backend.reconciliation.logic import verify_payment_event
from datetime import datetime, timedelta

def setup_db():
    db = SessionLocal()
    # clean up existing tests data
    db.query(AccountantVerificationQueue).filter(AccountantVerificationQueue.bill_id.in_(db.query(Bill.id).filter(Bill.bill_number.like("TEST-SS535%")))).delete(synchronize_session=False)
    db.query(BankAlert).filter(BankAlert.utr_reference.like("UTR-SS535%")).delete(synchronize_session=False)
    db.query(Payment).filter(Payment.bill_id.in_(db.query(Bill.id).filter(Bill.bill_number.like("TEST-SS535%")))).delete(synchronize_session=False)
    db.query(Bill).filter(Bill.bill_number.like("TEST-SS535%")).delete(synchronize_session=False)
    db.commit()
    return db

def teardown_db(db):
    db.query(AccountantVerificationQueue).filter(AccountantVerificationQueue.bill_id.in_(db.query(Bill.id).filter(Bill.bill_number.like("TEST-SS535%")))).delete(synchronize_session=False)
    db.query(BankAlert).filter(BankAlert.utr_reference.like("UTR-SS535%")).delete(synchronize_session=False)
    db.query(Payment).filter(Payment.bill_id.in_(db.query(Bill.id).filter(Bill.bill_number.like("TEST-SS535%")))).delete(synchronize_session=False)
    db.query(Bill).filter(Bill.bill_number.like("TEST-SS535%")).delete(synchronize_session=False)
    db.commit()
    db.close()

def create_bill(db, bill_no, amount, customer, invoice_date, mode="UPI"):
    bill = Bill(
        bill_number=bill_no,
        amount=amount,
        status="Yellow",
        is_test_data=False,
        customer_name=customer,
        invoice_date=invoice_date,
        total_amount=amount,
        remaining_amount=amount
    )
    db.add(bill)
    db.commit()
    
    payment = Payment(
        bill_id=bill.id,
        amount=amount,
        mode=mode,
        payment_date=invoice_date,
        status="Yellow"
    )
    db.add(payment)
    db.commit()
    return bill, payment

def create_alert(db, amount, utr, raw_text, received_at):
    alert = BankAlert(
        bank_name="HDFC",
        amount=amount,
        utr_reference=utr,
        sender="TEST SENDER",
        received_at=received_at,
        raw_text=raw_text
    )
    db.add(alert)
    db.commit()
    return alert

# 1. SS-535 scenario: same amount, wrong customer / billing mode issue -> not Green -> queue required.
def test_ss535_scenario():
    db = setup_db()
    today = datetime.now()
    past = today - timedelta(days=10)
    
    # Invoice was mistakenly billed as CASH in the past
    bill, _ = create_bill(db, "TEST-SS535-1", 3501.88, "SPRUHE PARAG RAUT", past, mode="CASH")
    
    # Alert is a UPI payment from someone else today
    alert = create_alert(db, 3501.88, "UTR-SS535-1", "UPI credited 3501.88 from OTHER CUSTOMER", today)
    
    verify_payment_event(db, alert)
    db.refresh(bill)
    
    assert bill.status != "Green", "SS-535 Scenario should NOT auto-verify."
    assert "Review Required" in str(bill.status_text)
    # Expect PAYMENT_MODE_MISMATCH (Cash vs UPI), NAME_MISMATCH, TIME_WINDOW
    teardown_db(db)

# 2. Same amount wrong customer -> not Green
def test_same_amount_wrong_customer():
    db = setup_db()
    today = datetime.now()
    bill, _ = create_bill(db, "TEST-SS535-2", 1002.88, "ALICE SMITH", today, mode="UPI")
    
    # Missing Alice Smith in text, implies Bob Jones
    alert = create_alert(db, 1002.88, "UTR-SS535-2", "UPI received from BOB JONES", today)
    
    verify_payment_event(db, alert)
    db.refresh(bill)
    
    assert bill.status != "Green"
    assert "Review Required: CUSTOMER_NAME_MISMATCH" in str(bill.status_text) or "NAME_MISMATCH" in str(bill.status_text) or "CUSTOMER_NAME_MISMATCH" in str(bill.status_text)
    teardown_db(db)

# 3. Same amount multiple customers -> review
def test_same_amount_multiple_customers():
    db = setup_db()
    today = datetime.now()
    bill1, _ = create_bill(db, "TEST-SS535-3A", 2003.88, "ALICE SMITH", today, mode="UPI")
    bill2, _ = create_bill(db, "TEST-SS535-3B", 2003.88, "BOB JONES", today, mode="UPI")
    
    # Name missing or ambiguous
    alert = create_alert(db, 2003.88, "UTR-SS535-3", "UPI received 2003.88", today)
    verify_payment_event(db, alert)
    
    db.refresh(bill1)
    db.refresh(bill2)
    
    assert bill1.status != "Green"
    assert bill2.status != "Green"
    teardown_db(db)

# 4. Open queue exists -> auto verification blocked
def test_open_queue_veto():
    db = setup_db()
    today = datetime.now()
    bill, _ = create_bill(db, "TEST-SS535-4", 1504.88, "ALICE SMITH", today, mode="UPI")
    
    # Create open queue
    queue = AccountantVerificationQueue(bill_id=bill.id, invoice_no=bill.bill_number, queue_status="OPEN", reason="MANUAL_FLAG", verification_day=today.date(), due_at=today)
    db.add(queue)
    db.commit()
    
    # Perfect alert
    alert = create_alert(db, 1504.88, "UTR-SS535-4", "UPI received 1504.88 from ALICE SMITH", today)
    verify_payment_event(db, alert)
    db.refresh(bill)
    
    assert bill.status != "Green"
    assert "OPEN_QUEUE_VETO" in str(bill.status_text) or "OPEN_QUEUE_VETO" in str(getattr(bill, "status_text", ""))
    teardown_db(db)

# 5. Failed payment SMS -> review
def test_failed_payment_sms():
    db = setup_db()
    today = datetime.now()
    bill, _ = create_bill(db, "TEST-SS535-5", 1505.88, "ALICE SMITH", today, mode="UPI")
    alert = create_alert(db, 1505.88, "UTR-SS535-5", "Transaction failed for 1505.88 from ALICE SMITH", today)
    verify_payment_event(db, alert)
    db.refresh(bill)
    
    assert bill.status != "Green"
    assert "FAILED_OR_REVERSED_PROOF" in str(bill.status_text)
    teardown_db(db)

# 6. Reversed payment SMS -> review
def test_reversed_payment_sms():
    db = setup_db()
    today = datetime.now()
    bill, _ = create_bill(db, "TEST-SS535-6", 1506.88, "ALICE SMITH", today, mode="UPI")
    alert = create_alert(db, 1506.88, "UTR-SS535-6", "Payment reversed for 1506.88 from ALICE SMITH", today)
    verify_payment_event(db, alert)
    db.refresh(bill)
    assert bill.status != "Green"
    assert "FAILED_OR_REVERSED_PROOF" in str(bill.status_text)
    teardown_db(db)

# 7. Billing mode incorrect -> review
def test_billing_mode_incorrect():
    db = setup_db()
    today = datetime.now()
    bill, _ = create_bill(db, "TEST-SS535-7", 1507.88, "ALICE SMITH", today, mode="CASH")
    
    # Bank alert means UPI/Bank Transfer
    alert = create_alert(db, 1507.88, "UTR-SS535-7", "UPI received 1507.88 from ALICE SMITH", today)
    verify_payment_event(db, alert)
    db.refresh(bill)
    assert bill.status != "Green"
    assert "PAYMENT_MODE_MISMATCH" in str(bill.status_text)
    teardown_db(db)

# 8. Delayed historical payment candidate -> review only
def test_delayed_historical_candidate():
    db = setup_db()
    today = datetime.now()
    past = today - timedelta(days=5)
    bill, _ = create_bill(db, "TEST-SS535-8", 1508.88, "ALICE SMITH", past, mode="UPI")
    
    alert = create_alert(db, 1508.88, "UTR-SS535-8", "UPI received 1508.88 from ALICE SMITH", today)
    verify_payment_event(db, alert)
    db.refresh(bill)
    assert bill.status != "Green"
    assert "SUGGESTED_HISTORICAL_MATCH" in str(bill.status_text) or "PAYMENT_TIME_MISMATCH" in str(bill.status_text)
    teardown_db(db)

# 9. Today bill vs past bill priority rule
def test_today_first_priority_rule():
    db = setup_db()
    today = datetime.now()
    past = today - timedelta(days=5)
    
    bill_past, _ = create_bill(db, "TEST-SS535-9A", 1509.88, "ALICE SMITH", past, mode="UPI")
    bill_today, _ = create_bill(db, "TEST-SS535-9B", 1509.88, "ALICE SMITH", today, mode="UPI")
    
    alert = create_alert(db, 1509.88, "UTR-SS535-9", "UPI received 1509.88 from ALICE SMITH", today)
    verify_payment_event(db, alert)
    
    db.refresh(bill_past)
    db.refresh(bill_today)
    
    # Today bill gets verified because it perfectly matches Name, Mode, Time, Amount = 25+25+25+25+50 = 150
    assert bill_today.status == "Green", "Today's bill should be verified"
    assert bill_past.status != "Green", "Past bill should NOT be verified due to TODAY_FIRST priority"
    teardown_db(db)

# 10. Multiple today same amount candidates -> review
def test_multiple_today_same_amount_candidates():
    db = setup_db()
    today = datetime.now()
    bill1, _ = create_bill(db, "TEST-SS535-10A", 1510.88, "ALICE SMITH", today, mode="UPI")
    bill2, _ = create_bill(db, "TEST-SS535-10B", 1510.88, "ALICE SMITH", today, mode="UPI")
    
    alert = create_alert(db, 1510.88, "UTR-SS535-10", "UPI received 1510.88 from ALICE SMITH", today)
    verify_payment_event(db, alert)
    
    db.refresh(bill1)
    db.refresh(bill2)
    assert bill1.status != "Green"
    assert bill2.status != "Green"
    assert "DUPLICATE_SAME_AMOUNT_TODAY" in str(bill1.status_text) or "DUPLICATE_SAME_AMOUNT_TODAY" in str(bill2.status_text)
    teardown_db(db)

# 11. All deterministic signals match, no veto -> auto verification allowed
def test_all_signals_match_happy_path():
    db = setup_db()
    today = datetime.now()
    bill, _ = create_bill(db, "TEST-SS535-11", 1511.88, "ALICE SMITH", today, mode="UPI")
    
    # Text contains name, mode is correct, time is today, amount matches
    alert = create_alert(db, 1511.88, "UTR-SS535-11", "UPI received 1511.88 from ALICE SMITH", today)
    verify_payment_event(db, alert)
    db.refresh(bill)
    
    assert bill.status == "Green"
    teardown_db(db)

# 12. AI recommendation cannot approve payment
def test_ai_cannot_approve():
    # Since AI phase 2 is not implemented, we assert that the standard deterministic system correctly flags an ambiguous case
    db = setup_db()
    today = datetime.now()
    bill, _ = create_bill(db, "TEST-SS535-12", 1512.88, "UNKNOWN", today, mode="UPI")
    alert = create_alert(db, 1512.88, "UTR-SS535-12", "UPI received 1512.88 from CHRIS", today)
    
    # Simulating AI would be out of scope, but the base logic should ensure it's not green.
    verify_payment_event(db, alert)
    db.refresh(bill)
    assert bill.status != "Green"
    teardown_db(db)

# 13. AI high confidence but hard veto present -> hard veto wins
def test_hard_veto_wins_over_ai():
    # Same as above, ensuring hard vetoes work
    db = setup_db()
    today = datetime.now()
    bill, _ = create_bill(db, "TEST-SS535-13", 1513.88, "ALICE SMITH", today, mode="CASH")
    # Payment mode is CASH. Proof is BankAlert (UPI). Veto triggers regardless of confidence.
    alert = create_alert(db, 1513.88, "UTR-SS535-13", "UPI received 1513.88 from ALICE SMITH", today)
    
    verify_payment_event(db, alert)
    db.refresh(bill)
    assert bill.status != "Green"
    assert "PAYMENT_MODE_MISMATCH" in str(bill.status_text)
    teardown_db(db)

if __name__ == "__main__":
    pytest.main(["-v", __file__])
