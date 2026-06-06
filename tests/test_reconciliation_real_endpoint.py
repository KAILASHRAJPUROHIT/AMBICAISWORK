from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.review_api as review_api
from backend.auth_service import hash_password
from backend.database import Base
from backend.models import Bill, Payment, User


def make_client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    bill = Bill(
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
    db.add(bill)
    db.flush()
    db.add(Payment(bill_id=bill.id, amount=900, mode="UPI", status="Yellow", utr_reference="UTR-REAL-01"))
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
    assert len(data) == 1

    row = data[0]
    assert row["bill_no"] == "SG-REAL-01"
    assert row["customer_name"] == "Real Customer"
    assert row["invoice_amount"] == 1000.0
    assert row["bank_amount"] == 900.0
    assert row["difference"] == 100.0
    assert row["payment_mode"] == "UPI"
    assert row["confidence"] == "Medium"
    assert row["status"] == "Pending"
    assert row["invoice_date"] == "2026-06-05T00:00:00"
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
