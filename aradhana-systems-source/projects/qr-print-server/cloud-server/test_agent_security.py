"""Queue files and state are visible only to the local print agent."""
import app as a


def test_agent_queue_requires_bearer_token(monkeypatch):
    monkeypatch.setenv("AGENT_TOKEN", "unit-agent-token")
    client = a.app.test_client()

    assert client.get("/api/agent/jobs/pending").status_code == 401
    assert client.get("/api/agent/jobs/pending", headers={
        "Authorization": "Bearer unit-agent-token"
    }).status_code == 200


def test_agent_media_requires_bearer_token(monkeypatch):
    monkeypatch.setenv("AGENT_TOKEN", "unit-agent-token")
    client = a.app.test_client()

    assert client.get("/media/unknown/file.pdf").status_code == 401
