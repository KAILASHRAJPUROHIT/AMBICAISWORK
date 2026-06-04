import pytest
from fastapi.testclient import TestClient
from backend.review_api import app
from backend.database import SessionLocal
from backend.models import User, Bill
import json

client = TestClient(app)

def test_system_health_fields():
    response = client.get("/api/system/health")
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

def test_reconciliations_endpoint():
    response = client.get("/api/reconciliations")
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

def test_escalations_endpoint():
    response = client.get("/api/escalations/open")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

def test_reports_owner_endpoint():
    response = client.get("/api/reports/owner")
    assert response.status_code == 200
    data = response.json()
    assert "daily_summary" in data
    assert "report_date" in data

def test_extraction_review_endpoint():
    response = client.get("/api/prime/manual-report-import/latest")
    assert response.status_code == 200
    data = response.json()
    assert "records" in data
