import importlib.util
from pathlib import Path


APP = Path(__file__).parents[1] / "app.py"
spec = importlib.util.spec_from_file_location("ais_control_center", APP)
control_center = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control_center)


def test_health_is_available_only_on_loopback():
    client = control_center.app.test_client()
    assert client.get("/health").get_json()["status"] == "healthy"
    denied = client.get("/health", environ_overrides={"REMOTE_ADDR": "192.168.0.44"})
    assert denied.status_code == 403


def test_registry_exposes_inventory_without_secret_fields():
    response = control_center.app.test_client().get("/api/v1/registry")
    payload = response.get_json()
    assert payload["registry"]["platform"] == "AIS"
    assert any(item["id"] == "document-print-workflow" for item in payload["registry"]["plugins"])
    rendered = str(payload).lower()
    assert "token" not in rendered and "password" not in rendered and "private" not in rendered
