import pytest
from fastapi.testclient import TestClient
from backend.review_api import app
from backend.database import SessionLocal
from backend.models import User, Session as SessionModel
from datetime import datetime, timedelta

client = TestClient(app)

def test_unauthenticated_api_rejected():
    response = client.get("/api/reports/owner")
    assert response.status_code == 401

def test_invalid_token_rejected():
    response = client.get("/api/reports/owner", headers={"X-Session-Token": "invalid_token"})
    assert response.status_code == 401

def test_public_endpoint_accessible():
    response = client.get("/api/version")
    assert response.status_code == 200

def test_validate_session_flow():
    db = SessionLocal()
    # 1. Setup test user
    emp_id = "TEST-AUTH-GUARD"
    user = db.query(User).filter(User.employee_id == emp_id).first()
    if not user:
        user = User(employee_id=emp_id, name="Guard Test", email="guard@test.com", role="OWNER", is_active=1)
        db.add(user)
        db.commit()

    # 2. Create session
    token = "VALID-TEST-TOKEN-999"
    db.query(SessionModel).filter(SessionModel.session_token == token).delete()
    session = SessionModel(employee_id=emp_id, session_token=token, expires_at=datetime.now() + timedelta(hours=1))
    db.add(session)
    db.commit()
    db.close()

    # 3. Call validate-session
    response = client.get("/api/auth/validate-session", headers={"X-Session-Token": token})
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["user"]["employee_id"] == emp_id

    # 4. Access protected route
    response = client.get("/api/reports/owner", headers={"X-Session-Token": token})
    assert response.status_code == 200

