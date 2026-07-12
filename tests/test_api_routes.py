from fastapi.testclient import TestClient
from backend.main import app  # Import the main FastAPI app
from backend.rbac import UserRole, Permission
from backend.review_queue_manager import _reviews_db
from backend.owner_escalation import _escalations_db
from datetime import datetime, timedelta

# Create a TestClient instance for the main FastAPI app
client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_permissions_endpoint_accountant():
    response = client.get("/permissions/accountant")
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "accountant"
    assert "view_reviews" in data["permissions"]
    assert "resolve_reviews" in data["permissions"]
    assert "view_escalations" not in data["permissions"]


def test_permissions_endpoint_owner():
    response = client.get("/permissions/owner")
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "owner"
    assert "view_escalations" in data["permissions"]
    assert "resolve_escalations" in data["permissions"]
    assert "view_reports" in data["permissions"]
    # Owner is the superuser and also holds review permissions in the current model.
    assert "view_reviews" in data["permissions"]


def test_permissions_endpoint_admin():
    response = client.get("/permissions/admin")
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "admin"
    assert "view_reviews" in data["permissions"]
    assert "manage_users" in data["permissions"]


def test_permissions_endpoint_invalid_role():
    response = client.get("/permissions/unknown_role")
    assert response.status_code == 404
    assert response.json() == {"detail": "Role not found"}


def test_open_reviews_endpoint():
    # Clear dbs for deterministic testing
    _reviews_db.clear()

    response = client.get("/reviews/open")
    assert response.status_code == 200
    reviews = response.json()
    assert len(reviews) == 2  # Based on dummy data in api_routes.py
    assert any(r["review_id"] == "mock_review_1" for r in reviews)
    assert any(r["review_id"] == "mock_review_2" for r in reviews)


def test_open_escalations_endpoint():
    # Clear dbs for deterministic testing
    _escalations_db.clear()

    response = client.get("/escalations/open")
    assert response.status_code == 200
    escalations = response.json()
    assert len(escalations) == 2  # Based on dummy data in api_routes.py
    assert any(e["escalation_id"] == "mock_esc_1" for e in escalations)
    assert any(e["escalation_id"] == "mock_esc_2" for e in escalations)


def test_owner_report_endpoint():
    response = client.get("/reports/owner")
    assert response.status_code == 200
    report = response.json()
    assert "generated_at" in report
    assert "report_date" in report
    assert report["processed_count"] == 100
    assert report["open_reviews"] == 5
    assert report["escalated_reviews"] == 2
    assert report["high_risk_count"] == 1
    assert report["critical_risk_count"] == 1
    assert report["owner_action_required"] is True
    assert "report_lines" in report
    assert any("CRITICAL ESCALATION: Review ID rev_crit_001" in line for line in report["report_lines"])
    assert any("HIGH ESCALATION: Review ID rev_high_002" in line for line in report["report_lines"])


def test_no_unsafe_write_methods_exposed():
    # Attempt to use non-GET methods on the defined GET endpoints
    # These should all return 405 Method Not Allowed

    # /health
    response = client.post("/health")
    assert response.status_code == 405

    # /permissions/{role}
    response = client.post("/permissions/admin")
    assert response.status_code == 405

    # /reviews/open
    response = client.post("/reviews/open")
    assert response.status_code == 405

    # /escalations/open
    response = client.post("/escalations/open")
    assert response.status_code == 405
    
    # /reports/owner
    response = client.post("/reports/owner")
    assert response.status_code == 405
