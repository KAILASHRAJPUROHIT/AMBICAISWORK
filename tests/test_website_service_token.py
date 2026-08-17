"""Covers the X-Website-Service-Token gate in app.py -- the mechanism that
lets ambicdigital-website's server-to-server proxy reach both
/api/website-auth/* and the general API surface without a browser session.
"""
import app as catalogue_app


def _client():
    return catalogue_app.app.test_client()


def test_website_auth_requires_a_token_at_all():
    response = _client().post("/api/website-auth/session", json={"email": "x", "auth_version": 0})
    assert response.status_code == 401
    assert response.get_json()["ok"] is False


def test_website_auth_rejects_wrong_token():
    response = _client().post(
        "/api/website-auth/session",
        json={"email": "x", "auth_version": 0},
        headers={"X-Website-Service-Token": "not-the-real-token"},
    )
    assert response.status_code == 401


def test_website_auth_accepts_valid_token_without_any_browser_session():
    response = _client().post(
        "/api/website-auth/session",
        json={"email": "nobody@example.com", "auth_version": 0},
        headers={"X-Website-Service-Token": catalogue_app.WEBSITE_SERVICE_TOKEN},
    )
    assert response.status_code == 200
    assert response.get_json() == {"ok": False}  # valid token, but no such owner


def test_website_auth_unknown_action_is_404_even_with_a_valid_token():
    response = _client().post(
        "/api/website-auth/not-a-real-action",
        json={},
        headers={"X-Website-Service-Token": catalogue_app.WEBSITE_SERVICE_TOKEN},
    )
    assert response.status_code == 404


def test_a_browser_session_alone_never_satisfies_website_auth():
    client = _client()
    with client.session_transaction() as session:
        session["authed"] = True
    response = client.post("/api/website-auth/session", json={"email": "x", "auth_version": 0})
    assert response.status_code == 401


def test_valid_service_token_also_authorizes_the_general_api_surface():
    # The website's [...path] proxy calls ordinary API routes (api/health-
    # style endpoints, not just /api/website-auth/*) with this same header
    # on behalf of an already-authenticated owner -- no session cookie
    # involved. Confirm the token alone gets past require_login() for a
    # route that would otherwise 401.
    client = _client()
    unauthed = client.get("/api/pipeline/dashboard")
    assert unauthed.status_code == 401
    authed = client.get(
        "/api/pipeline/dashboard",
        headers={"X-Website-Service-Token": catalogue_app.WEBSITE_SERVICE_TOKEN},
    )
    assert authed.status_code == 200
