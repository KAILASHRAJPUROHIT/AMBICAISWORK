from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

import backend.review_api as review_api
from backend.database import Base
from backend.models import User, AuditLog
from backend.auth_service import hash_password


def make_client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    db.add_all([
        User(employee_id="OWNER-01", name="Owner", role="OWNER", email="owner@example.com", hashed_password=hash_password("owner"), is_active=1),
        User(employee_id="ACC-01", name="Accountant", role="ACCOUNTANT", email="acc@example.com", hashed_password=hash_password("acc"), is_active=1),
        User(employee_id="MIGRATED-1-ABC", name="newadmin", role="STAFF", email=None, hashed_password=hash_password("x"), is_active=0),
        User(employee_id="TEST-OWNER-02", name="Test Owner", role="OWNER", email="test@example.com", hashed_password=hash_password("x"), is_active=1),
    ])
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
        if token == "staff-token":
            return "ACC-01"
        return None

    review_api.app.dependency_overrides.clear()
    monkeypatch.setitem(review_api.app.dependency_overrides, review_api.get_db, override_get_db)
    monkeypatch.setattr(review_api, "validate_session", fake_validate_session)
    return TestClient(review_api.app), TestingSessionLocal


def test_owner_can_list_users_with_default_filters(monkeypatch):
    client, _ = make_client(monkeypatch)
    response = client.get("/api/admin/users", headers={"X-Session-Token": "owner-token"})
    assert response.status_code == 200
    employee_ids = [u["employee_id"] for u in response.json()]
    assert "OWNER-01" in employee_ids
    assert "ACC-01" in employee_ids
    assert "MIGRATED-1-ABC" not in employee_ids
    assert "TEST-OWNER-02" not in employee_ids


def test_include_filters_reveal_hidden_users(monkeypatch):
    client, _ = make_client(monkeypatch)
    response = client.get(
        "/api/admin/users?include_inactive=true&include_archived=true&include_test=true",
        headers={"X-Session-Token": "owner-token"},
    )
    assert response.status_code == 200
    employee_ids = [u["employee_id"] for u in response.json()]
    assert "MIGRATED-1-ABC" in employee_ids
    assert "TEST-OWNER-02" in employee_ids


def test_non_owner_cannot_manage_users(monkeypatch):
    client, _ = make_client(monkeypatch)
    response = client.get("/api/admin/users", headers={"X-Session-Token": "staff-token"})
    assert response.status_code == 403


def test_password_hash_is_never_returned(monkeypatch):
    client, _ = make_client(monkeypatch)
    response = client.post(
        "/api/admin/users",
        headers={"X-Session-Token": "owner-token"},
        json={
            "employee_id": "DEV-01",
            "name": "Developer",
            "email": "dev@example.com",
            "role": "DEVELOPER",
            "password": "Temporary123",
            "permissions": ["dashboard_access", "audit_logs_access"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "hashed_password" not in str(payload)
    assert "Temporary123" not in str(payload)


def test_archive_does_not_delete_user(monkeypatch):
    client, SessionLocal = make_client(monkeypatch)
    response = client.post("/api/admin/users/ACC-01/archive", headers={"X-Session-Token": "owner-token"})
    assert response.status_code == 200

    default_list = client.get("/api/admin/users", headers={"X-Session-Token": "owner-token"}).json()
    assert "ACC-01" not in [u["employee_id"] for u in default_list]

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.employee_id == "ACC-01").count() == 1
    finally:
        db.close()


def test_update_user_logs_audit_event(monkeypatch):
    client, SessionLocal = make_client(monkeypatch)
    response = client.patch(
        "/api/admin/users/ACC-01",
        headers={"X-Session-Token": "owner-token"},
        json={"name": "Senior Accountant", "permissions": ["dashboard_access", "reports_access"]},
    )
    assert response.status_code == 200

    db = SessionLocal()
    try:
        actions = [log.action for log in db.query(AuditLog).all()]
        assert "USER_UPDATED" in actions
        assert "PERMISSIONS_UPDATED" in actions
    finally:
        db.close()
