import pytest
from fastapi.testclient import TestClient
from backend.review_api import app
from backend.database import SessionLocal
from backend.models import User, Session as SessionModel
import json
from datetime import datetime, timedelta

client = TestClient(app)

@pytest.fixture
def auth_header():
    db = SessionLocal()
    # Create test owner
    employee_id = "TEST-OWNER-02"
    user = db.query(User).filter(User.employee_id == employee_id).first()
    if not user:
        user = User(
            employee_id=employee_id,
            name="Test Owner",
            email="owner2@test.com",
            role="OWNER",
            is_active=1
        )
        db.add(user)
        db.commit()
    
    # Create session
    token = "TEST-SESSION-TOKEN-02"
    session = db.query(SessionModel).filter(SessionModel.session_token == token).first()
    if not session:
        session = SessionModel(
            employee_id=employee_id,
            session_token=token,
            expires_at=datetime.now() + timedelta(hours=1)
        )
        db.add(session)
        db.commit()
    
    db.close()
    return {"X-Session-Token": token}

def test_system_health_fields(auth_header):
    response = client.get("/api/system/health", headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    assert "services" in data
    assert "invoice_watcher" in data["services"]
    assert "bank_email_poller" in data["services"]
    assert "android_sms_relay" in data["services"]
    
    # Check for specific fields in each service
    for service in ["invoice_watcher", "bank_email_poller", "android_sms_relay"]:
        assert "status" in data["services"][service]
        assert "last_polled_at" in data["services"][service]
        assert "event_count" in data["services"][service]
        assert "error" in data["services"][service]

def test_reconciliations_endpoint(auth_header):
    response = client.get("/api/reconciliations", headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        item = data[0]
        assert "invoice_no" in item
        assert "status" in item
        assert "invoice_date" in item
        assert "details" in item
        assert "customer" in item["details"]
        assert "total" in item["details"]
        assert "payments" in item["details"]
        assert "mode" in item["details"]
        assert "invoice_url" in item["details"]
        assert "proof_url" in item["details"]

def test_escalations_endpoint(auth_header):
    response = client.get("/api/escalations/open", headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data

def test_reports_owner_endpoint(auth_header):
    response = client.get("/api/reports/owner", headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    assert "daily_summary" in data
    assert "report_date" in data

def test_extraction_review_endpoint(auth_header):
    response = client.get("/api/prime/manual-report-import/latest", headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
