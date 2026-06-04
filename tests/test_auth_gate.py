import pytest
from fastapi.testclient import TestClient
from backend.review_api import app

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

