from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.review_api as review_api
from backend.auth_service import hash_password
from backend.database import Base
from backend.models import BankAlert, Bill, Payment, SMSAlert, User


def make_client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    partial_bill = Bill(
        bill_number="SG-REAL-01",
        customer_name="Real Customer",
        amount=1000,
        payment_mode="UPI",
        status="Yellow",
        review_required=1,
        is_test_data=False,
        invoice_date=datetime(2026, 6, 5),
        invoice_generated_at=datetime(2026, 6, 5, 10, 30),
        created_at=datetime(2026, 6, 5, 10, 35),
    )
    exact_upi_bill = Bill(
        bill_number="SG-UPI-EXACT-01",
        customer_name="UPI Customer",
        amount=1000,
        payment_mode="UPI",
        status="Yellow",
        review_required=1,
        is_test_data=False,
        invoice_date=datetime(2026, 6, 5),
        invoice_generated_at=datetime(2026, 6, 5, 11, 30),
        created_at=datetime(2026, 6, 5, 11, 35),
    )
    old_gold_bill = Bill(
        bill_number="SG-OLDGOLD-01",
        customer_name="Old Gold Customer",
        amount=145542,
        payment_mode="OLD_GOLD_EXCHANGE,CARD",
        status="Yellow",
        review_required=1,
        is_test_data=False,
        invoice_date=datetime(2026, 6, 5),
        invoice_generated_at=datetime(2026, 6, 5, 12, 30),
        created_at=datetime(2026, 6, 5, 12, 35),
    )
    advance_bill = Bill(
        bill_number="SG-ADVANCE-01",
        customer_name="Advance Customer",
        amount=25000,
        payment_mode="ADVANCE,UPI",
        status="Yellow",
        review_required=1,
        is_test_data=False,
        invoice_date=datetime(2026, 6, 5),
        invoice_generated_at=datetime(2026, 6, 5, 13, 30),
        created_at=datetime(2026, 6, 5, 13, 35),
    )
    no_utr_bill = Bill(
        bill_number="SG-NOUTR-01",
        customer_name="No UTR Customer",
        amount=777,
        payment_mode="BANK_TRANSFER",
        status="Yellow",
        review_required=1,
        is_test_data=False,
        invoice_date=datetime(2026, 6, 5),
        invoice_generated_at=datetime(2026, 6, 5, 14, 30),
        created_at=datetime(2026, 6, 5, 14, 35),
    )
    verified_bills = [
        Bill(
            bill_number=f"SG-VERIFIED-{index:02d}",
            customer_name=f"Verified Customer {index}",
            amount=100 + index,
            payment_mode="UPI",
            status="Green",
            review_required=0,
            is_test_data=False,
            invoice_date=datetime(2026, 6, 5),
            invoice_generated_at=datetime(2026, 6, 5, 15, index),
            created_at=datetime(2026, 6, 5, 15, index, 30),
        )
        for index in range(1, 16)
    ]
    db.add_all([partial_bill, exact_upi_bill, old_gold_bill, advance_bill, no_utr_bill, *verified_bills])
    db.flush()
    db.add(Payment(bill_id=partial_bill.id, amount=900, mode="UPI", status="Yellow", utr_reference="UTR-REAL-01", payment_date=datetime(2026, 6, 5, 10, 45)))
    db.add(Payment(bill_id=exact_upi_bill.id, amount=1000, mode="UPI", status="Yellow", utr_reference="UTR-UPI-EXACT", payment_date=datetime(2026, 6, 5, 11, 45)))
    db.add(Payment(bill_id=old_gold_bill.id, amount=145542, mode="OLD_GOLD_EXCHANGE,CARD", status="Yellow", utr_reference="UTR-OLDGOLD", payment_date=datetime(2026, 6, 5, 12, 45)))
    db.add(Payment(bill_id=advance_bill.id, amount=25000, mode="ADVANCE,UPI", status="Yellow", utr_reference="UTR-ADVANCE", payment_date=datetime(2026, 6, 5, 13, 45)))
    db.add(Payment(bill_id=no_utr_bill.id, amount=777, mode="BANK_TRANSFER", status="Yellow", payment_date=datetime(2026, 6, 5, 14, 45)))
    for index, bill in enumerate(verified_bills, start=1):
        db.add(Payment(bill_id=bill.id, amount=100 + index, mode="UPI", status="Green", utr_reference=f"UTR-VERIFIED-{index:02d}", payment_date=datetime(2026, 6, 5, 15, index, 45)))
    db.add(SMSAlert(
        sms_id="SMS-REAL-01",
        sender="ICICIB",
        transaction_timestamp=datetime(2026, 6, 5, 10, 44),
        bank_name="ICICI",
        amount=900,
        utr_reference="UTR-REAL-01",
        raw_body="Credited INR 900 UTR UTR-REAL-01",
        parsed_confidence=1.0,
    ))
    db.add(BankAlert(
        bank_name="ICICI",
        amount=1000,
        utr_reference="UTR-UPI-EXACT",
        sender="alerts@icicibank.com",
        received_at=datetime(2026, 6, 5, 11, 44),
        raw_text="Credited INR 1000 UTR UTR-UPI-EXACT",
    ))
    db.add(BankAlert(
        bank_name="ICICI",
        amount=777,
        utr_reference="BANK-NO-UTR-MATCH",
        sender="ICICI",
        received_at=datetime(2026, 6, 5, 14, 46),
        raw_text="Credited INR 777 without invoice UTR",
    ))
    db.add(Bill(bill_number="TEST-REAL-02", customer_name="Test", amount=1, status="Yellow", review_required=1, is_test_data=False))
    db.add(Bill(bill_number="ARCH-REAL-03", customer_name="Archive", amount=1, status="Yellow", review_required=1, is_test_data=False))
    db.add(Bill(bill_number="HARDENING-REAL-04", customer_name="Hardening", amount=1, status="Yellow", review_required=1, is_test_data=False))
    db.add(Bill(bill_number="SG-TESTDATA-01", customer_name="Test Data", amount=1, status="Yellow", review_required=1, is_test_data=True))
    db.add(User(employee_id="OWNER-01", name="Owner", role="OWNER", email="owner@example.com", hashed_password=hash_password("owner"), is_active=1))
    db.commit()
    db.close()

    def override_get_db():
        local_db = TestingSessionLocal()
        try:
            yield local_db
        finally:
            local_db.close()

    def fake_validate_session(_db, token):
        if token == "owner-token":
            return "OWNER-01"
        return None

    review_api.app.dependency_overrides.clear()
    monkeypatch.setitem(review_api.app.dependency_overrides, review_api.get_db, override_get_db)
    monkeypatch.setattr(review_api, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(review_api, "validate_session", fake_validate_session)
    return TestClient(review_api.app)


def test_real_reconciliation_endpoint_returns_json_array(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/reconciliation/open", headers={"X-Session-Token": "owner-token"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 20
    assert response.headers["x-reconciliation-total-considered"] == "23"
    assert response.headers["x-reconciliation-rows-returned"] == "20"
    assert response.headers["x-reconciliation-excluded-test-prefix"] == "1"
    assert response.headers["x-reconciliation-excluded-archive-prefix"] == "1"
    assert response.headers["x-reconciliation-excluded-hardening-prefix"] == "1"
    assert response.headers["x-reconciliation-excluded-test-data"] == "1"

    row = next(item for item in data if item["bill_no"] == "SG-REAL-01")
    assert row["bill_no"] == "SG-REAL-01"
    assert row["customer_name"] == "Real Customer"
    assert row["invoice_amount"] == 1000.0
    assert row["bank_amount"] == 900.0
    assert row["difference"] == 100.0
    assert row["payment_mode"] == "UPI"
    assert row["confidence"] == "Medium"
    assert row["status"] == "Pending"
    assert row["invoice_date"] == "2026-06-05T00:00:00"
    assert row["invoice_timestamp"] == "2026-06-05T10:30:00"
    assert row["invoice_timestamp_source"] == "invoice_generated_at"
    assert row["invoice_time_recorded"] is True
    # Display contract: electronic modes show the payment UTR as the reference,
    # and proof_label describes the verified proof ("Verified by <type> Proof (ID: n)").
    assert row["payment_breakdown"][0] == {
        "amount": 900.0,
        "mode": "UPI",
        "timestamp": "2026-06-05T10:45:00",
        "utr_reference": "UTR-REAL-01",
        "reference": "UTR-REAL-01",
        "source": "SMS",
        "proof_url": "/api/reconciliation/proof/sms/1",
        "proof_label": "Verified by SMS Proof (ID: 1)",
    }

    exact_upi = next(item for item in data if item["bill_no"] == "SG-UPI-EXACT-01")
    assert exact_upi["confidence"] == "High"
    assert exact_upi["status"] == "Verified"
    assert exact_upi["difference"] == 0.0
    assert exact_upi["has_special_payment_flag"] is False
    assert exact_upi["payment_breakdown"][0]["source"] == "Bank"
    assert exact_upi["payment_breakdown"][0]["proof_label"] == "Verified by Bank Proof (ID: 1)"

    no_utr = next(item for item in data if item["bill_no"] == "SG-NOUTR-01")
    assert no_utr["payment_breakdown"][0]["source"] == "Bank"
    # No UTR on the payment + amount-only proof match => reference is not surfaced
    # and the proof is reported as a partial (conservative; not auto-confirmed).
    assert no_utr["payment_breakdown"][0]["reference"] is None
    assert no_utr["payment_breakdown"][0]["proof_label"] == (
        "Partial Proof from Bank (ID: 2): Amount matches, UTR differs/missing"
    )

    verified = next(item for item in data if item["bill_no"] == "SG-VERIFIED-01")
    assert verified["status"] == "Verified"
    assert verified["confidence"] == "High"

    old_gold = next(item for item in data if item["bill_no"] == "SG-OLDGOLD-01")
    assert old_gold["difference"] == 0.0
    assert old_gold["confidence"] == "Medium"
    assert old_gold["status"] == "ACCOUNTANT APPROVAL REQUIRED"
    assert old_gold["has_special_payment_flag"] is True

    advance = next(item for item in data if item["bill_no"] == "SG-ADVANCE-01")
    assert advance["difference"] == 0.0
    assert advance["confidence"] == "Medium"
    assert advance["status"] == "ACCOUNTANT APPROVAL REQUIRED"
    assert advance["has_special_payment_flag"] is True

    assert "mock_review_1" not in str(data)
    assert "pay_001" not in str(data)
    assert "bill_002" not in str(data)
    assert "TEST-REAL-02" not in str(data)
    assert "ARCH-REAL-03" not in str(data)
    assert "HARDENING-REAL-04" not in str(data)


def test_real_reconciliation_endpoint_requires_session(monkeypatch):
    client = make_client(monkeypatch)

    missing = client.get("/api/reconciliation/open")
    assert missing.status_code == 401
    assert missing.headers["content-type"].startswith("application/json")

    expired = client.get("/api/reconciliation/open", headers={"X-Session-Token": "bad-token"})
    assert expired.status_code == 401
    assert expired.headers["content-type"].startswith("application/json")


def test_reconciliation_proof_preview_requires_session_and_returns_text(monkeypatch):
    client = make_client(monkeypatch)

    missing = client.get("/api/reconciliation/proof/sms/1")
    assert missing.status_code == 401

    sms = client.get("/api/reconciliation/proof/sms/1", headers={"X-Session-Token": "owner-token"})
    assert sms.status_code == 200
    assert sms.headers["content-type"].startswith("text/plain")
    assert "SMS PAYMENT PROOF" in sms.text
    assert "UTR-REAL-01" in sms.text

    bank = client.get("/api/reconciliation/proof/bank/1", headers={"X-Session-Token": "owner-token"})
    assert bank.status_code == 200
    assert bank.headers["content-type"].startswith("text/plain")
    assert "BANK / EMAIL PAYMENT PROOF" in bank.text
    assert "UTR-UPI-EXACT" in bank.text
