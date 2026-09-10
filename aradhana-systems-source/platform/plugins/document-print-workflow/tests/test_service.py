import importlib.util
from pathlib import Path

APP = Path(__file__).parents[1] / "service" / "app.py"
spec = importlib.util.spec_from_file_location("workflow", APP)
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


def test_biller_must_explicitly_attach(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "DB_PATH", tmp_path / "workflow.db")
    workflow.init_db()
    client = workflow.app.test_client()
    bundle = client.post("/api/v1/document-bundles", json={"display_name": "Riya Shah — Aadhaar + PAN"}).get_json()["id"]
    session = client.post("/api/v1/print-sessions", json={"customer_name": "Riya Shah"}).get_json()["id"]
    assert client.post(f"/api/v1/print-sessions/{session}/decision", json={"decision": "attach"}).status_code == 409
    result = client.post(f"/api/v1/print-sessions/{session}/decision", json={"decision": "attach", "bundle_id": bundle})
    assert result.status_code == 200
    assert result.get_json()["bundle_id"] == bundle


def test_wait_has_a_60_second_deadline(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "DB_PATH", tmp_path / "workflow.db")
    workflow.init_db()
    client = workflow.app.test_client()
    session = client.post("/api/v1/print-sessions", json={}).get_json()["id"]
    result = client.post(f"/api/v1/print-sessions/{session}/decision", json={"decision": "wait"})
    assert result.status_code == 200
    assert result.get_json()["wait_until"]


def test_health_and_print_outcome_are_observable(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "DB_PATH", tmp_path / "workflow.db")
    workflow.init_db()
    client = workflow.app.test_client()
    session = client.post("/api/v1/print-sessions", json={}).get_json()["id"]
    assert client.get("/health").get_json()["status"] == "healthy"
    result = client.post(f"/api/v1/print-sessions/{session}/outcome", json={"outcome": "spooled"})
    assert result.status_code == 200
    assert result.get_json()["status"] == "spooled"


def test_stale_bundle_is_never_offered_to_biller(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "DB_PATH", tmp_path / "workflow.db")
    workflow.init_db()
    client = workflow.app.test_client()
    stale = (workflow.utcnow() - workflow.timedelta(minutes=31)).isoformat()
    bundle = client.post("/api/v1/document-bundles", json={"bundle_id": "DOC-STALE", "display_name": "Old scan", "created_at": stale})
    assert bundle.status_code == 201
    listed = client.get("/api/v1/document-bundles").get_json()["bundles"]
    assert listed == []


def test_current_ui_does_not_offer_a_bill_print_action(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "DB_PATH", tmp_path / "workflow.db")
    workflow.init_db()
    response = workflow.app.test_client().post("/api/v1/print-sessions", json={})
    assert response.get_json()["options"] == ["attach", "standalone", "bill_only"]


def test_reconcile_removes_claimed_cloud_bundle_and_keeps_current_choices(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "DB_PATH", tmp_path / "workflow.db")
    workflow.init_db()
    client = workflow.app.test_client()
    first = client.post("/api/v1/document-bundles", json={
        "bundle_id": "DOC-DIRECT", "display_name": "Direct print ID"
    }).get_json()["id"]
    second = client.post("/api/v1/document-bundles", json={
        "bundle_id": "DOC-BILLER", "display_name": "Biller queue ID"
    }).get_json()["id"]

    result = client.post("/api/v1/document-bundles/reconcile", json={"bundle_ids": [second]})
    assert result.status_code == 200
    assert result.get_json()["removed"] == 1
    listed = client.get("/api/v1/document-bundles").get_json()["bundles"]
    assert [bundle["id"] for bundle in listed] == [second]
    assert first != second


def test_sync_reoffers_unclaimed_provisional_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "DB_PATH", tmp_path / "workflow.db")
    workflow.init_db()
    client = workflow.app.test_client()
    bundle = client.post("/api/v1/document-bundles", json={
        "bundle_id": "DOC-RETRY", "display_name": "Retry document"
    }).get_json()["id"]
    session = client.post("/api/v1/print-sessions", json={}).get_json()["id"]
    assert client.post(f"/api/v1/print-sessions/{session}/decision", json={
        "decision": "attach", "bundle_id": bundle
    }).status_code == 200
    # The cloud still presenting this ID means the earlier claim failed;
    # syncing must return it to the next biller instead of hiding it.
    response = client.post("/api/v1/document-bundles", json={
        "bundle_id": bundle, "display_name": "Retry document"
    })
    assert response.get_json()["status"] == "pending"
    assert client.get("/api/v1/document-bundles").get_json()["bundles"][0]["id"] == bundle
