from __future__ import annotations

import app as catalogue_app


def test_password_then_email_otp_required(monkeypatch):
    sent = {}
    monkeypatch.setattr(catalogue_app.email_2fa, "configured", lambda: True)
    monkeypatch.setattr(catalogue_app.email_2fa, "send_otp", lambda code: sent.setdefault("code", code))
    client = catalogue_app.app.test_client()

    response = client.post(
        "/login?next=/dashboard",
        data={"password": catalogue_app.ADMIN_PASSWORD},
        environ_base={"REMOTE_ADDR": "198.51.100.20"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/verify-otp")
    assert len(sent["code"]) == 6

    blocked = client.get("/dashboard")
    assert blocked.status_code == 302
    assert "/login" in blocked.headers["Location"]

    verified = client.post("/verify-otp", data={"code": sent["code"]})
    assert verified.status_code == 302
    assert verified.headers["Location"].endswith("/dashboard")
    assert client.get("/dashboard").status_code == 200


def test_email_2fa_must_be_configured(monkeypatch):
    monkeypatch.setattr(catalogue_app.email_2fa, "configured", lambda: False)
    client = catalogue_app.app.test_client()
    response = client.post(
        "/login",
        data={"password": catalogue_app.ADMIN_PASSWORD},
        environ_base={"REMOTE_ADDR": "198.51.100.21"},
    )
    assert response.status_code == 503
    assert b"Email 2FA is not configured" in response.data


def test_wrong_otp_does_not_authenticate(monkeypatch):
    monkeypatch.setattr(catalogue_app.email_2fa, "configured", lambda: True)
    monkeypatch.setattr(catalogue_app.email_2fa, "send_otp", lambda code: None)
    client = catalogue_app.app.test_client()
    client.post(
        "/login",
        data={"password": catalogue_app.ADMIN_PASSWORD},
        environ_base={"REMOTE_ADDR": "198.51.100.22"},
    )
    response = client.post("/verify-otp", data={"code": "000000"})
    assert response.status_code == 200
    assert b"Incorrect verification code" in response.data
    assert client.get("/").status_code == 302
