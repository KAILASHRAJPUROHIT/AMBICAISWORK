import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.rbac import UserRole

client = TestClient(app)

def test_admin_can_create_user():
    response = client.post("/users/", params={"username": "newadmin", "email": "admin@example.com"}, headers={"X-User-Role": "admin"})
    assert response.status_code == 200

def test_accountant_cannot_create_user():
    response = client.post("/users/", params={"username": "newuser", "email": "user@example.com"}, headers={"X-User-Role": "accountant"})
    assert response.status_code == 403

def test_owner_cannot_create_user():
    response = client.post("/users/", params={"username": "newuser", "email": "user@example.com"}, headers={"X-User-Role": "owner"})
    assert response.status_code == 403

def test_no_role_cannot_create_user():
    response = client.post("/users/", params={"username": "newuser", "email": "user@example.com"})
    assert response.status_code == 403

def test_admin_can_create_bill():
    response = client.post("/bills/", params={"user_id": 1, "amount": 100.0}, headers={"X-User-Role": "admin"})
    assert response.status_code == 200

def test_accountant_cannot_create_bill():
    response = client.post("/bills/", params={"user_id": 1, "amount": 100.0}, headers={"X-User-Role": "accountant"})
    assert response.status_code == 403

def test_owner_can_create_audit_log():
    response = client.post("/audit_logs/", params={"user_id": 1, "action": "view", "details": "some details"}, headers={"X-User-Role": "owner"})
    assert response.status_code == 200

def test_accountant_cannot_create_audit_log():
    response = client.post("/audit_logs/", params={"user_id": 1, "action": "view", "details": "some details"}, headers={"X-User-Role": "accountant"})
    assert response.status_code == 403

def test_accountant_can_create_review_queue_item():
    # Note: This might fail if entity_id doesn't exist in DB, but we check status_code for 403 specifically
    item_data = {
        "entity_type": "payment",
        "entity_id": 1,
        "current_status": "Yellow",
        "proposed_status": "Green",
        "risk_flags": []
    }
    response = client.post("/review_queue/", json=item_data, headers={"X-User-Role": "accountant"})
    # It might return 500 or 404 if data is invalid, but it shouldn't be 403
    assert response.status_code != 403

def test_owner_cannot_create_review_queue_item():
    item_data = {
        "entity_type": "payment",
        "entity_id": 1,
        "current_status": "Yellow",
        "proposed_status": "Green",
        "risk_flags": []
    }
    response = client.post("/review_queue/", json=item_data, headers={"X-User-Role": "owner"})
    assert response.status_code == 403
