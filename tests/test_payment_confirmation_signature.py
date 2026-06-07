from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.models import BankAlert, Bill, Payment, PaymentConfirmationSignature, SMSAlert
from backend.payment_confirmation_signature import build_payment_confirmation_signature


def make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def test_ss534_style_missing_payment_utr_does_not_verify():
    db = make_db()
    bill = Bill(
        bill_number="SS-534",
        customer_name="KALIDAS CHINTAMAN MEHER",
        amount=11000,
        payment_mode="UPI",
        status="Yellow",
        status_text="Pending",
        review_required=1,
        is_test_data=False,
        invoice_date=datetime(2026, 6, 7),
        invoice_generated_at=datetime(2026, 6, 7, 15, 26, 55),
        created_at=datetime(2026, 6, 7, 10, 0, 0),
    )
    db.add(bill)
    db.flush()
    payment = Payment(
        bill_id=bill.id,
        amount=11000,
        mode="UPI",
        status="Yellow",
        utr_reference=None,
        payment_date=None,
        created_at=datetime(2026, 6, 7, 10, 0, 0),
    )
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
        raw_text="SMS Forwarded via Email: Credited Rs 11000. Ref No 615856728999.",
        reconciled=True,
    ))
    db.commit()

    signature = build_payment_confirmation_signature(db, bill.id)

    assert signature["payment_status"] == "REVIEW_REQUIRED"
    assert signature["confidence_level"] != "HIGH"
    assert signature["proof_status"] == "PARTIAL_PROOF"
    assert signature["proof_source"] == "SMS"
    assert signature["proof_reference"] == "615856728999"
    assert signature["proof_timestamp"] == datetime(2026, 6, 7, 15, 22, 27)
    assert signature["requires_accountant_review"] is True
    assert signature["verification_state"] == "ACCOUNTANT_REVIEW"
    assert "payment row missing UTR" in signature["confidence_reason"]

    unchanged_payment = db.query(Payment).filter(Payment.id == payment.id).first()
    unchanged_bill = db.query(Bill).filter(Bill.id == bill.id).first()
    assert unchanged_payment.utr_reference is None
    assert unchanged_payment.payment_date is None
    assert unchanged_bill.status == "Yellow"


def test_exact_upi_signature_requires_payment_utr_and_timestamp_alignment():
    db = make_db()
    bill = Bill(
        bill_number="SS-EXACT",
        customer_name="Exact Customer",
        amount=5000,
        payment_mode="UPI",
        status="Yellow",
        review_required=1,
        is_test_data=False,
        invoice_date=datetime(2026, 6, 7),
        created_at=datetime(2026, 6, 7, 12, 0, 0),
    )
    db.add(bill)
    db.flush()
    db.add(Payment(
        bill_id=bill.id,
        amount=5000,
        mode="UPI",
        status="Yellow",
        utr_reference="UTR-EXACT",
        payment_date=datetime(2026, 6, 7, 12, 10, 0),
    ))
    db.add(SMSAlert(
        sender="BANK",
        transaction_timestamp=datetime(2026, 6, 7, 12, 9, 0),
        bank_name="ICICI",
        amount=5000,
        utr_reference="UTR-EXACT",
        raw_body="Credited Rs 5000 UTR UTR-EXACT.",
        parsed_confidence=1.0,
    ))
    db.commit()

    signature = build_payment_confirmation_signature(db, bill.id)

    assert signature["payment_status"] == "VERIFIED"
    assert signature["confidence_level"] == "EXACT"
    assert signature["proof_status"] == "EXACT_PROOF"
    assert signature["requires_accountant_review"] is False
    assert signature["verification_state"] == "SYSTEM_VERIFIED"


def test_signature_model_table_is_registered():
    assert PaymentConfirmationSignature.__tablename__ == "payment_confirmation_signatures"
