from fastapi.testclient import TestClient
from backend.review_api import app

client = TestClient(app)

def test_debug_runtime_json():
    response = client.get("/debug/runtime")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "cwd" in data
    assert "database_path" in data
    assert "invoice_count" in data
    print("\nDebug Runtime Response:", data)

def test_debug_startup_json():
    response = client.get("/debug/startup")
    assert response.status_code == 200
    data = response.json()
    assert "project_root" in data
    assert "bills_table_exists" in data
    assert data["bills_table_exists"] is True
    print("\nDebug Startup Response:", data)

def test_production_safety_status_contract():
    response = client.get("/debug/production-safety")
    assert response.status_code == 200
    data = response.json()
    for key in [
        "environment",
        "database_path",
        "frontend_port",
        "backend_port",
        "chosen_pdf_watch_path",
        "watcher_status",
        "watcher_running",
        "pdf_count",
        "last_scan",
        "legacy_alerts_enabled",
        "update_channel",
    ]:
        assert key in data
    assert data["update_channel"] == "STABLE"
    assert isinstance(data["legacy_alerts_enabled"], bool)
