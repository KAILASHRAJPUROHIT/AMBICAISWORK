"""Regression tests for GET /api/auth/me.

A valid session whose user account no longer exists (archived/deleted) must
return a clean 401 — NOT a 500. A 500 here is read by the SPA as an auth failure,
which clears the session and bounces the user to /login on every load
(a "login loop").
"""
from fastapi.testclient import TestClient

from backend.review_api import app
from backend.database import SessionLocal
from backend.auth_service import create_user_session

client = TestClient(app)


def test_auth_me_missing_user_returns_401_not_500():
    db = SessionLocal()
    try:
        # Session for an employee_id with no matching User row.
        token = create_user_session(db, "GHOST-DOES-NOT-EXIST")
    finally:
        db.close()

    resp = client.get("/api/auth/me", headers={"X-Session-Token": token})
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/json")


def test_auth_me_without_token_returns_401():
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
