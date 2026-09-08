from fastapi.testclient import TestClient

from app import main
from app.main import app


def test_health_is_public_and_healthy():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_owner_api_requires_a_bearer_token():
    response = TestClient(app).get("/api/v1/dashboard")
    assert response.status_code == 401


def test_public_module_routes_exist():
    response = TestClient(app).get("/documents")
    assert response.status_code == 200
    assert "Aradhana Intelligence System" in response.text


def test_configured_owner_login_creates_a_session(monkeypatch):
    monkeypatch.setattr(main, "ADMIN_CREDENTIAL_HASH", "8da193366e1554c08b2870c50f737b9587c3372b656151c4a96028af26f51334")
    monkeypatch.setattr(main, "SESSION_SECRET", "test-only-session-secret")
    client = TestClient(app)
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    assert client.get("/api/v1/dashboard").status_code == 200
