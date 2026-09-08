import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app


def test_dashboard_html_is_never_cached(monkeypatch):
    monkeypatch.setattr(app, "ADMIN_PASSWORD", "test-password")
    client = app.app.test_client()
    client.post("/login", data={"password": "test-password"})

    response = client.get("/")

    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"
