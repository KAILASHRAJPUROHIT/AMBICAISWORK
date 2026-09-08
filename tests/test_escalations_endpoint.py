"""Contract tests for GET /api/escalations/open.

An escalation is a non-test, undelivered bill the reconciliation engine classifies
as "Risk / Mismatch" (CRITICAL) or "ACCOUNTANT APPROVAL REQUIRED" (HIGH). Ordinary
pending / verified bills are NOT escalations.
"""
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.review_api as review_api
from backend.database import Base
from backend.models import Bill, Payment


def make_client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    # HIGH: advance / old-gold mode -> ACCOUNTANT APPROVAL REQUIRED
    approval = Bill(bill_number="SG-APPROVAL-01", customer_name="Approval Cust", amount=25000,
                    payment_mode="ADVANCE,UPI", status="Yellow", review_required=1,
                    is_test_data=False, is_delivered=False, invoice_date=datetime(2026, 6, 5))
    # CRITICAL: overpayment -> negative difference -> Risk / Mismatch
    risk = Bill(bill_number="SG-RISK-01", customer_name="Risk Cust", amount=1000,
                payment_mode="UPI", status="Yellow", review_required=1,
                is_test_data=False, is_delivered=False, invoice_date=datetime(2026, 6, 5))
    # NOT an escalation: exact match -> Verified
    verified = Bill(bill_number="SG-OK-01", customer_name="Ok Cust", amount=1000,
                    payment_mode="UPI", status="Green", review_required=0,
                    is_test_data=False, is_delivered=False, invoice_date=datetime(2026, 6, 5))
    # NOT an escalation: partial -> Pending
    pending = Bill(bill_number="SG-PENDING-01", customer_name="Pending Cust", amount=1000,
                   payment_mode="UPI", status="Yellow", review_required=1,
                   is_test_data=False, is_delivered=False, invoice_date=datetime(2026, 6, 5))
    # Excluded: test data
    testdata = Bill(bill_number="SG-TD-01", customer_name="TD", amount=25000, payment_mode="ADVANCE",
                    status="Yellow", review_required=1, is_test_data=True, invoice_date=datetime(2026, 6, 5))
    # Excluded: delivered (resolved)
    delivered = Bill(bill_number="SG-DONE-01", customer_name="Done", amount=25000, payment_mode="ADVANCE",
                     status="Yellow", review_required=1, is_test_data=False, is_delivered=True,
                     invoice_date=datetime(2026, 6, 5))
    db.add_all([approval, risk, verified, pending, testdata, delivered])
    db.flush()
    db.add(Payment(bill_id=approval.id, amount=25000, mode="ADVANCE,UPI", status="Yellow"))
    db.add(Payment(bill_id=risk.id, amount=1200, mode="UPI", status="Yellow"))  # overpaid
    db.add(Payment(bill_id=verified.id, amount=1000, mode="UPI", status="Green"))
    db.add(Payment(bill_id=pending.id, amount=500, mode="UPI", status="Yellow"))
    db.add(Payment(bill_id=delivered.id, amount=25000, mode="ADVANCE", status="Yellow"))
    db.commit()
    db.close()

    def override_get_db():
        local = TestingSessionLocal()
        try:
            yield local
        finally:
            local.close()

    def fake_validate_session(_db, token):
        return "OWNER-01" if token == "owner-token" else None

    review_api.app.dependency_overrides.clear()
    monkeypatch.setitem(review_api.app.dependency_overrides, review_api.get_db, override_get_db)
    monkeypatch.setattr(review_api, "validate_session", fake_validate_session)
    return TestClient(review_api.app)


def test_escalations_requires_session(monkeypatch):
    client = make_client(monkeypatch)
    assert client.get("/api/escalations/open").status_code == 401
    assert client.get("/api/escalations/open", headers={"X-Session-Token": "bad"}).status_code == 401


def test_escalations_only_risky_bills(monkeypatch):
    client = make_client(monkeypatch)
    r = client.get("/api/escalations/open", headers={"X-Session-Token": "owner-token"})
    assert r.status_code == 200
    data = r.json()

    bills = {e["bill_no"]: e for e in data["escalations"]}
    assert set(bills) == {"SG-APPROVAL-01", "SG-RISK-01"}
    assert data["count"] == 2
    assert data["critical_count"] == 1
    assert data["high_count"] == 1

    assert bills["SG-APPROVAL-01"]["severity"] == "HIGH"
    assert bills["SG-APPROVAL-01"]["reason"] == "ACCOUNTANT APPROVAL REQUIRED"
    assert bills["SG-RISK-01"]["severity"] == "CRITICAL"
    assert bills["SG-RISK-01"]["reason"] == "Risk / Mismatch"

    # Excluded states must never appear.
    for excluded in ("SG-OK-01", "SG-PENDING-01", "SG-TD-01", "SG-DONE-01"):
        assert excluded not in bills

    # CRITICAL sorts before HIGH.
    assert data["escalations"][0]["severity"] == "CRITICAL"
