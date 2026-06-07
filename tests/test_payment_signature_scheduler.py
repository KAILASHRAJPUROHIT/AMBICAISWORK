from datetime import datetime, timedelta

import backend.payment_signature_scheduler as scheduler
from backend.models import AuditLog, BankAlert, Bill, Payment, PaymentConfirmationSignature, SMSAlert
from tests.test_payment_confirmation_signature import make_db


def bind_scheduler(monkeypatch, db):
    class SessionFactory:
        def __call__(self):
            return db

    monkeypatch.setattr(scheduler, "SessionLocal", SessionFactory())
    monkeypatch.setattr(scheduler, "ensure_signature_table", lambda: None)


def test_today_signature_dry_run_does_not_mutate_bill_or_payment(monkeypatch):
    db = make_db()
    bill = Bill(
        bill_number="SS-534",
        customer_name="Customer",
        amount=11000,
        payment_mode="UPI",
        status="Yellow",
        status_text="Pending",
        review_required=1,
        is_test_data=False,
        invoice_date=datetime(2026, 6, 7),
        created_at=datetime(2026, 6, 7, 10, 0),
    )
    db.add(bill)
    db.flush()
    payment = Payment(bill_id=bill.id, amount=11000, mode="UPI", status="Yellow", created_at=datetime(2026, 6, 7, 10, 0))
    db.add(payment)
    db.add(SMSAlert(
        sender="JD-ICICIT-S",
        transaction_timestamp=datetime(2026, 6, 7, 15, 22, 27),
        bank_name="ICICI",
        amount=11000,
        utr_reference="615856728999",
        raw_body="Credited Rs 11000. Ref No 615856728999.",
        parsed_confidence=1.0,
    ))
    db.add(BankAlert(
        bank_name="ICICI",
        amount=11000,
        utr_reference="615856728999",
        sender="JD-ICICIT-S",
        received_at=datetime(2026, 6, 7, 15, 22, 27),
        raw_text="Credited Rs 11000. Ref No 615856728999.",
    ))
    db.commit()
    bill_id = bill.id
    payment_id = payment.id
    bind_scheduler(monkeypatch, db)

    summary = scheduler.run_signature_rebuild_once("today", dry_run=True, now=datetime(2026, 6, 7, 16, 0))

    assert summary["candidate_count"] == 1
    assert summary["changed"] == 1
    assert summary["ss_534"]["payment_status"] == "REVIEW_REQUIRED"
    assert summary["ss_534"]["proof_status"] == "PARTIAL_PROOF"
    assert summary["ss_534"]["confidence_level"] != "HIGH"
    assert db.query(PaymentConfirmationSignature).count() == 0
    assert db.query(AuditLog).count() == 0
    assert db.query(Bill).filter(Bill.id == bill_id).first().status == "Yellow"
    assert db.query(Payment).filter(Payment.id == payment_id).first().status == "Yellow"


def test_today_signature_apply_only_writes_signature_and_audit(monkeypatch):
    db = make_db()
    bill = Bill(
        bill_number="SS-EXACT",
        amount=5000,
        payment_mode="UPI",
        status="Yellow",
        review_required=1,
        is_test_data=False,
        invoice_date=datetime(2026, 6, 7),
    )
    db.add(bill)
    db.flush()
    db.add(Payment(
        bill_id=bill.id,
        amount=5000,
        mode="UPI",
        status="Yellow",
        utr_reference="UTR-EXACT",
        payment_date=datetime(2026, 6, 7, 12, 0),
    ))
    db.add(SMSAlert(
        sender="BANK",
        transaction_timestamp=datetime(2026, 6, 7, 12, 1),
        amount=5000,
        utr_reference="UTR-EXACT",
        raw_body="Credited Rs 5000 UTR UTR-EXACT.",
        parsed_confidence=1.0,
    ))
    db.commit()
    bill_id = bill.id
    bind_scheduler(monkeypatch, db)

    summary = scheduler.run_signature_rebuild_once("today", dry_run=False, now=datetime(2026, 6, 7, 16, 0))

    assert summary["created"] == 1
    assert db.query(PaymentConfirmationSignature).count() == 1
    assert db.query(AuditLog).filter(AuditLog.action == "PAYMENT_SIGNATURE_CREATED").count() == 1
    assert db.query(Bill).filter(Bill.id == bill_id).first().status == "Yellow"
    assert db.query(Payment).filter(Payment.bill_id == bill_id).first().status == "Yellow"


def test_historical_loop_skips_green_and_closed_signature(monkeypatch):
    db = make_db()
    old_open = Bill(
        bill_number="SS-OLD-OPEN",
        amount=1000,
        payment_mode="UPI",
        status="Yellow",
        is_test_data=False,
        invoice_date=datetime(2026, 6, 6),
    )
    old_green = Bill(
        bill_number="SS-OLD-GREEN",
        amount=1000,
        payment_mode="UPI",
        status="Green",
        is_test_data=False,
        invoice_date=datetime(2026, 6, 6),
    )
    closed_signature_bill = Bill(
        bill_number="SS-CLOSED-SIG",
        amount=1000,
        payment_mode="UPI",
        status="Yellow",
        is_test_data=False,
        invoice_date=datetime(2026, 6, 6),
    )
    db.add_all([old_open, old_green, closed_signature_bill])
    db.flush()
    db.add(PaymentConfirmationSignature(
        bill_id=closed_signature_bill.id,
        invoice_no=closed_signature_bill.bill_number,
        signature_version="PCS_V1",
        signature_hash="closed",
        invoice_amount=1000,
        matched_amount=1000,
        difference_amount=0,
        payment_mode="UPI",
        payment_status="ACCOUNTANT_VERIFIED",
        confidence_level="EXACT",
        confidence_score=100,
        confidence_reason="Manual close",
        proof_status="EXACT_PROOF",
        requires_accountant_review=False,
        requires_owner_review=False,
        verification_state="ACCOUNTANT_VERIFIED",
    ))
    db.commit()
    bind_scheduler(monkeypatch, db)

    summary = scheduler.run_signature_rebuild_once("historical", dry_run=True, now=datetime(2026, 6, 7, 16, 0))

    assert summary["candidate_count"] == 2
    assert summary["evaluated"] == 1
    assert summary["skipped_closed"] == 1
    assert summary["changed"] == 1


def test_scheduler_config_defaults_and_bounds(monkeypatch):
    monkeypatch.delenv("SIGNATURE_SCHEDULER_ENABLED", raising=False)
    monkeypatch.delenv("TODAY_SIGNATURE_REBUILD_INTERVAL_SECONDS", raising=False)
    monkeypatch.setenv("HISTORICAL_SIGNATURE_REBUILD_INTERVAL_SECONDS", "10")
    monkeypatch.setenv("SIGNATURE_REBUILD_LOOKBACK_DAYS", "0")

    config = scheduler.get_scheduler_config()

    assert config["enabled"] is False
    assert config["today_interval_seconds"] == 15
    assert config["historical_interval_seconds"] == 60
    assert config["lookback_days"] == 1
