from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.review_api as review_api
from backend.database import Base
from backend.models import SMSAlert


def make_client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = testing_session()
    db.add_all([
        SMSAlert(sender="ICICIB", transaction_timestamp=datetime(2026, 9, 2, 10, 30), bank_name="ICICI", account_suffix="XX1234", credit_or_debit="CREDIT", amount=12500, utr_reference="UPI123456", payer_name="Asha", raw_body="ICICI Bank: Account XX1234 credited with Rs 12,500 from Asha. UPI Ref: UPI123456"),
        # Older releases incorrectly stored all relay messages as CREDIT. The API must repair that at read time.
        SMSAlert(sender="HDFCBK", transaction_timestamp=datetime(2026, 9, 2, 11, 0), bank_name="HDFC", account_suffix="XX9876", credit_or_debit="CREDIT", amount=800, utr_reference="CARD999", payer_name=None, raw_body="HDFC A/c XX9876 debited by Rs 800 at Merchant Store via CARD. Ref No: CARD999"),
    ])
    db.commit(); db.close()
    def override_get_db():
        local = testing_session()
        try: yield local
        finally: local.close()
    review_api.app.dependency_overrides.clear()
    monkeypatch.setitem(review_api.app.dependency_overrides, review_api.get_db, override_get_db)
    monkeypatch.setattr(review_api, "validate_session", lambda _db, token: "OWNER-01" if token == "owner-token" else None)
    return TestClient(review_api.app, client=("192.168.0.50", 50000))


def test_bank_activity_is_available_without_login_on_lan(monkeypatch):
    client = make_client(monkeypatch)
    assert client.get("/api/bank-activity").status_code == 200


def test_bank_activity_rejects_non_lan_client(monkeypatch):
    client = make_client(monkeypatch)
    client = TestClient(review_api.app, client=("8.8.8.8", 50000))
    assert client.get("/api/bank-activity").status_code == 403


def test_bank_activity_splits_credits_and_debits_without_raw_sms(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/bank-activity", headers={"X-Session-Token": "owner-token"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["credits"]) == 1
    assert len(data["debits"]) == 1
    assert data["credits"][0]["counterparty"] == "Asha"
    assert data["debits"][0]["account"] == "XX9876"
    assert data["debits"][0]["mode"] == "CARD"
    assert "raw_body" not in data["credits"][0]
    assert "raw_body" not in data["debits"][0]
