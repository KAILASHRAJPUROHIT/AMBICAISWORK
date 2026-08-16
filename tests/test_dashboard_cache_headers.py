import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app


def test_dashboard_html_is_never_cached(monkeypatch):
    app.app.config["TESTING"] = True
    client = app.app.test_client()
    # Real login requires email 2FA (deliberate, see login()/verify_otp()) —
    # setting the session directly is how every other authenticated-route
    # test in this suite gets past that without weakening the real flow.
    with client.session_transaction() as session:
        session["authed"] = True

    response = client.get("/")

    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"
