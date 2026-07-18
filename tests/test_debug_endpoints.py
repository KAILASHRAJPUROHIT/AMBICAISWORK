import secrets
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend import business_registry
from backend.database import SessionLocal
from backend.models import Session as SessionModel
from backend.review_api import app


client = TestClient(app)


def _diagnostic_session():
    db = SessionLocal()
    token = secrets.token_urlsafe(24)
    db.add(
        SessionModel(
            session_token=token,
            employee_id="DIAGNOSTIC-TEST",
            expires_at=datetime.now() + timedelta(hours=1),
        )
    )
    db.commit()
    business_registry.register_session(token, "test-tenant")
    return db, token


def test_debug_endpoints_reject_anonymous_requests():
    assert client.get("/debug/runtime").status_code == 401
    assert client.get("/debug/startup").status_code == 401


def test_debug_runtime_json_for_authenticated_session():
    db, token = _diagnostic_session()
    try:
        response = client.get("/debug/runtime", headers={"X-Session-Token": token})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "cwd" in data
        assert "database_path" in data
        assert "invoice_count" in data
    finally:
        business_registry.forget_session(token)
        db.close()


def test_debug_startup_json_for_authenticated_session():
    db, token = _diagnostic_session()
    try:
        response = client.get("/debug/startup", headers={"X-Session-Token": token})
        assert response.status_code == 200
        data = response.json()
        assert "project_root" in data
        assert "bills_table_exists" in data
        assert data["bills_table_exists"] is True
    finally:
        business_registry.forget_session(token)
        db.close()
