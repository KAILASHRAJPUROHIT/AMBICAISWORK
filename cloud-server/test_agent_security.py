"""Queue files and state are visible only to the local print agent."""
import app as a


def test_health_is_available_without_agent_credentials():
    response = a.app.test_client().get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "healthy"}


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
