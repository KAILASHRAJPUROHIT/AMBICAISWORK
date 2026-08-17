"""Covers website_auth.py -- the backend contract for ambicdigital-website's
Catalogue Studio owner-auth proxy. All tests point website_auth.STORE_PATH
at a throwaway file under tmp_path; the real credential store under
tenants/ambic-digital-demo/ is never touched by this suite.
"""
import json

import pyotp
import pytest
from werkzeug.security import generate_password_hash

import website_auth

EMAIL = "owner@example.com"
PASSWORD = "correcthorsebattery"


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    store = tmp_path / "staff_users.json"
    store.write_text(json.dumps([{
        "id": 1,
        "email": EMAIL,
        "password_hash": generate_password_hash(PASSWORD, method="scrypt"),
        "role": "owner",
        "auth_version": 0,
    }]), encoding="utf-8")
    monkeypatch.setattr(website_auth, "STORE_PATH", store)
    return store


def test_login_rejects_wrong_password():
    assert website_auth.login(EMAIL, "wrong") == {"ok": False}


def test_login_rejects_unknown_email():
    assert website_auth.login("nobody@example.com", PASSWORD) == {"ok": False}


def test_login_succeeds_without_2fa_configured():
    result = website_auth.login(EMAIL, PASSWORD)
    assert result == {
        "ok": True, "role": "owner", "email": EMAIL,
        "auth_version": 0, "two_factor_required": False,
    }


def test_session_checks_auth_version():
    assert website_auth.verify_session(EMAIL, 0) == {"ok": True, "role": "owner", "email": EMAIL}
    assert website_auth.verify_session(EMAIL, 1) == {"ok": False}
    assert website_auth.verify_session("nobody@example.com", 0) == {"ok": False}


def test_full_two_factor_enrollment_and_login_cycle():
    begin = website_auth.begin_two_factor(EMAIL, 0, PASSWORD)
    assert begin["ok"] is True
    secret = begin["data"]["secret"]
    assert begin["data"]["otpauth_uri"].startswith("otpauth://totp/")

    # Wrong current password refuses to hand out a secret.
    assert website_auth.begin_two_factor(EMAIL, 0, "wrong") == {"ok": False}

    code = pyotp.TOTP(secret).now()
    confirm = website_auth.confirm_two_factor(EMAIL, 0, code)
    assert confirm == {"ok": True}

    # auth_version bumped by enabling 2FA -- the pre-enrollment version is
    # now stale and must stop validating.
    assert website_auth.verify_session(EMAIL, 0) == {"ok": False}
    assert website_auth.two_factor_status(EMAIL, 1) == {"ok": True, "data": {"enabled": True}}

    login = website_auth.login(EMAIL, PASSWORD)
    assert login["two_factor_required"] is True
    assert login["auth_version"] == 1

    code2 = pyotp.TOTP(secret).now()
    verified = website_auth.verify_second_factor(EMAIL, 1, code2)
    assert verified == {"ok": True, "role": "owner", "email": EMAIL, "auth_version": 1}


def test_verify_second_factor_rejects_wrong_code_and_missing_secret():
    # Never enrolled -- no secret to check against.
    assert website_auth.verify_second_factor(EMAIL, 0, "123456") == {"ok": False}

    begin = website_auth.begin_two_factor(EMAIL, 0, PASSWORD)
    secret = begin["data"]["secret"]
    website_auth.confirm_two_factor(EMAIL, 0, pyotp.TOTP(secret).now())
    assert website_auth.verify_second_factor(EMAIL, 1, "000000") == {"ok": False}


def test_confirm_two_factor_rejects_without_pending_secret():
    assert website_auth.confirm_two_factor(EMAIL, 0, "123456") == {"ok": False}


def test_disable_two_factor_requires_password_and_valid_code():
    begin = website_auth.begin_two_factor(EMAIL, 0, PASSWORD)
    secret = begin["data"]["secret"]
    website_auth.confirm_two_factor(EMAIL, 0, pyotp.TOTP(secret).now())

    assert website_auth.disable_two_factor(EMAIL, 1, "wrong", pyotp.TOTP(secret).now()) == {"ok": False}
    assert website_auth.disable_two_factor(EMAIL, 1, PASSWORD, "000000") == {"ok": False}

    result = website_auth.disable_two_factor(EMAIL, 1, PASSWORD, pyotp.TOTP(secret).now())
    assert result == {"ok": True}
    assert website_auth.two_factor_status(EMAIL, 2) == {"ok": True, "data": {"enabled": False}}


def test_change_password_invalidates_old_session_and_accepts_new_password():
    result = website_auth.change_password(EMAIL, PASSWORD, "brandnewpassword123")
    assert result == {"ok": True}
    assert website_auth.verify_session(EMAIL, 0) == {"ok": False}
    assert website_auth.verify_session(EMAIL, 1)["ok"] is True
    assert website_auth.login(EMAIL, PASSWORD) == {"ok": False}
    assert website_auth.login(EMAIL, "brandnewpassword123")["ok"] is True


def test_change_password_rejects_short_new_password():
    result = website_auth.change_password(EMAIL, PASSWORD, "short")
    assert result["ok"] is False
    assert "12 characters" in result["error"]


def test_password_reset_is_honestly_unconfigured():
    # No SMS provider is wired up -- must fail loudly, never fake success.
    assert website_auth.password_reset_request(EMAIL)["ok"] is False
    assert website_auth.password_reset_confirm()["ok"] is False
