import pytest
from fastapi.testclient import TestClient
from backend.review_api import app
from backend.database import SessionLocal
from backend.models import User
import uuid

client = TestClient(app)

@pytest.fixture
def auth_header():
    # Create a test owner user if not exists
    db = SessionLocal()
    owner = db.query(User).filter(User.role == "OWNER").first()
    if not owner:
        owner = User(
            employee_id="TEST-OWNER-01",
            name="Test Owner",
            email="owner@test.com",
            role="OWNER",
            is_active=1
        )
        db.add(owner)
        db.commit()
        db.refresh(owner)
    
    # Create a session token (mock or real)
    # Since we use validate_session in require_role, we need a real session or mock it.
    # For now, let's just see if the endpoints exist even if they return 401.
    token = "TEST-SESSION-TOKEN"
    # We might need to insert this token into the sessions table if we want a full test.
    db.close()
    return {"X-Session-Token": token}

def test_reports_owner_exists():
    response = client.get("/api/reports/owner")
    # Should be 200 or 401 (if auth is required)
    assert response.status_code in [200, 401]
    if response.status_code == 200:
        data = response.json()
        assert "daily_summary" in data

def test_reports_bifurcation_exists():
    response = client.get("/api/reports/payment-bifurcation")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

def test_prime_latest_exists():
    response = client.get("/api/prime/manual-report-import/latest")
    assert response.status_code == 200
    data = response.json()
    assert "records" in data

def test_escalations_open_exists():
    response = client.get("/api/escalations/open")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
