from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.review_api as review_api
from backend.auth_service import hash_password
from backend.database import Base
from backend.models import BankAlert, Bill, Payment, User


def make_client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    rows = [
        ("SG-HIGH-01", "Fully Matched", 1000, 1000, "UPI", "UTR-HIGH-01"),
        ("SG-MED-01", "Partial Customer", 1000, 600, "UPI", "UTR-MED-01"),
        ("SG-LOW-01", "No Evidence", 1000, 0, "BANK", None),
        ("SG-OLDGOLD-01", "Old Gold Exact", 145542, 145542, "OLD_GOLD_EXCHANGE,CARD", "UTR-OLDGOLD-01"),
        ("SG-ADVANCE-01", "Advance Exact", 20000, 20000, "ADVANCE,UPI", "UTR-ADVANCE-01"),
        ("SG-OLDGOLD-MISMATCH", "Old Gold Mismatch", 20000, 22000, "OLD_GOLD_EXCHANGE,CARD", "UTR-OLDGOLD-02"),
    ]
    for bill_no, customer, invoice_amount, payment_amount, mode, utr in rows:
        bill = Bill(
            bill_number=bill_no,
            customer_name=customer,
            amount=invoice_amount,
            payment_mode=mode,
            status="Yellow",
            review_required=1,
            is_test_data=False,
            invoice_date=datetime(2026, 6, 5),
            invoice_generated_at=datetime(2026, 6, 5, 10, 30),
            created_at=datetime(2026, 6, 5, 10, 35),
            reference_no=utr,
        )
        db.add(bill)
        db.flush()
        if payment_amount:
            db.add(Payment(
                bill_id=bill.id,
                amount=payment_amount,
                mode=mode,
                status="Yellow",
                utr_reference=utr,
                payment_date=datetime(2026, 6, 5, 10, 39),
            ))
            db.add(BankAlert(
                bank_name="ICICI",
                amount=payment_amount,
                utr_reference=utr,
                sender="BANK",
                received_at=datetime(2026, 6, 5, 10, 40),
                raw_text="credit",
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


def rows_by_bill(data):
    return {row["bill_no"]: row for row in data}


def test_real_reconciliation_endpoint_returns_operational_audit_rows(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/reconciliation/open", headers={"X-Session-Token": "owner-token"})

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 6

    bills = rows_by_bill(data)
    assert "SG-HIGH-01" in bills
    assert "TEST-REAL-02" not in bills
    assert "ARCH-REAL-03" not in bills
    assert "HARDENING-REAL-04" not in bills
    assert "SG-TESTDATA-01" not in bills
    assert "mock_review_1" not in str(data)
    assert "pay_001" not in str(data)
    assert "bill_002" not in str(data)


def test_reconciliation_difference_and_confidence_are_deterministic(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/reconciliation/open", headers={"X-Session-Token": "owner-token"})
    bills = rows_by_bill(response.json())

    assert bills["SG-HIGH-01"]["difference"] == 0.0
    assert bills["SG-HIGH-01"]["outstanding"] == 0.0
    assert bills["SG-HIGH-01"]["confidence"] == "High"
    assert bills["SG-HIGH-01"]["difference_type"] == "zero"

    assert bills["SG-MED-01"]["difference"] == 400.0
    assert bills["SG-MED-01"]["outstanding"] == 400.0
    assert bills["SG-MED-01"]["confidence"] == "Medium"
    assert bills["SG-MED-01"]["difference_type"] == "outstanding"

    assert bills["SG-LOW-01"]["difference"] == 1000.0
    assert bills["SG-LOW-01"]["confidence"] == "Low"


def test_reconciliation_payment_timeline_shape(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/reconciliation/open", headers={"X-Session-Token": "owner-token"})
    row = rows_by_bill(response.json())["SG-MED-01"]

    assert row["payment_breakdown"] == [{
        "amount": 600.0,
        "mode": "UPI",
        "timestamp": "2026-06-05T10:39:00",
        "utr_reference": "UTR-MED-01",
        "reference": "UTR-MED-01",
        "source": "BANK",
        "evidence_link": None,
        "evidence_available": True,
    }]
    assert row["total_received"] == 600.0
    assert row["status_explanation"] == "Partial payment received. Outstanding balance remains."
    assert row["created_at"] is not None
    assert row["source_system"] == "ARADHANA_BILLS"


def test_master_safety_rule_blocks_old_gold_and_advance_auto_clear(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/reconciliation/open", headers={"X-Session-Token": "owner-token"})
    bills = rows_by_bill(response.json())

    old_gold = bills["SG-OLDGOLD-01"]
    assert old_gold["difference"] == 0.0
    assert old_gold["confidence"] == "Medium"
    assert old_gold["status"] == "ACCOUNTANT APPROVAL REQUIRED"
    assert old_gold["status_color"] == "PURPLE"
    assert old_gold["review_required"] is True
    assert old_gold["status_explanation"] == "Old gold exchange or advance payment requires accountant approval even though amounts may match."

    advance = bills["SG-ADVANCE-01"]
    assert advance["difference"] == 0.0
    assert advance["confidence"] == "Medium"
    assert advance["status"] == "ACCOUNTANT APPROVAL REQUIRED"
    assert advance["review_required"] is True

    normal_upi = bills["SG-HIGH-01"]
    assert normal_upi["difference"] == 0.0
    assert normal_upi["confidence"] == "High"
    assert normal_upi["status"] == "CLEAR"

    old_gold_mismatch = bills["SG-OLDGOLD-MISMATCH"]
    assert old_gold_mismatch["difference"] == -2000.0
    assert old_gold_mismatch["confidence"] == "Medium"
    assert old_gold_mismatch["status"] == "RISK / MISMATCH"
