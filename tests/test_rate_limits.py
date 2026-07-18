from fastapi.testclient import TestClient

from backend.review_api import _RATE_EVENTS, app


client = TestClient(app)


def test_password_recovery_rate_limit_returns_retry_after():
    _RATE_EVENTS.clear()
    try:
        for _ in range(5):
            response = client.post(
                "/api/auth/forgot-password",
                headers={"X-Business-Slug": "test-tenant"},
                json={"email": "missing@example.com"},
            )
            assert response.status_code == 200

        limited = client.post(
            "/api/auth/forgot-password",
            headers={"X-Business-Slug": "test-tenant"},
            json={"email": "missing@example.com"},
        )
        assert limited.status_code == 429
        assert int(limited.headers["Retry-After"]) > 0
    finally:
        _RATE_EVENTS.clear()
