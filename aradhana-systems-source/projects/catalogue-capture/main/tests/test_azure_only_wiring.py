import app


def _client():
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["authed"] = True
    return client


def test_azure_run_requires_process_password():
    client = _client()
    assert client.post("/api/process/start", json={"category": "earrings"}).status_code == 403
    assert client.post(
        "/api/process/start",
        json={"category": "earrings", "process_password": "wrong"},
    ).status_code == 403


def test_azure_run_accepts_authorized_start(monkeypatch):
    class ThreadWithoutStart:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(
        app,
        "_derive_single_items_from_disk",
        lambda: [{"pair": 1, "jewel": "x.jpg", "label": "X", "folder": app.INPUT}],
    )
    monkeypatch.setattr(app.prompt_governance, "approval_status", lambda: {"approved": True})
    monkeypatch.setattr(app.threading, "Thread", ThreadWithoutStart)
    app.CGPT_JOB["running"] = False
    response = _client().post(
        "/api/process/start",
        json={"category": "earrings", "process_password": "Aradhana@2026"},
    )
    app.CGPT_JOB["running"] = False
    assert response.status_code == 200
    assert response.get_json()["engine"] == "azure_flux2_pro"


def test_legacy_processing_routes_are_disabled():
    client = _client()
    for path in ("/api/copilot_run", "/api/chatgpt_run", "/api/codex_run", "/api/chat/send"):
        assert client.post(path, json={}).status_code == 404


def test_engine_switch_and_unattended_legacy_routes_are_locked():
    client = _client()
    assert client.get("/api/engine/config").get_json()["engine_mode"] == "azure_flux2_pro"
    assert client.post("/api/engine/config", json={"engine_mode": "local"}).status_code == 403
    assert client.post("/api/pipeline2/config", json={"enabled": True}).status_code == 404
    assert client.post("/api/auto_config", json={"enabled": True}).status_code == 404
