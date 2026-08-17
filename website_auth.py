"""Backend contract for ambicdigital-website's Catalogue Studio owner-auth
proxy (src/lib/catalogueStudioAuth.ts, src/app/api/catalogue-studio/auth/*).

Every function here is called server-to-server from the website's Next.js
API routes, behind a verified X-Website-Service-Token header (see
_valid_service_token() in app.py) -- never directly by a browser, and never
via the session-cookie login this Flask app also has for local/LAN use.
The website owns the only real user-facing login surface for this account;
this module just answers "is this real" for each step of that flow.

Field names in the returned dicts are load-bearing: catalogueStudioAuth.ts
reads result.data.secret / result.data.otpauth_uri / result.data.enabled /
result.auth_version / result.two_factor_required literally.
"""
from __future__ import annotations

import json
from pathlib import Path

import pyotp
from werkzeug.security import check_password_hash, generate_password_hash

BASE = Path(__file__).resolve().parent
STORE_PATH = BASE / "tenants" / "ambic-digital-demo" / "staff_users.json"
TOTP_ISSUER = "AMBIC Catalogue Studio"
MIN_PASSWORD_LENGTH = 12


def _load_users() -> list[dict]:
    if not STORE_PATH.is_file():
        return []
    return json.loads(STORE_PATH.read_text(encoding="utf-8"))


def _save_users(users: list[dict]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(users, indent=2), encoding="utf-8")


def _find_owner(email: str) -> tuple[list[dict], dict | None]:
    users = _load_users()
    needle = (email or "").strip().lower()
    for user in users:
        if user.get("role") == "owner" and str(user.get("email", "")).strip().lower() == needle:
            return users, user
    return users, None


def _version_matches(user: dict, auth_version) -> bool:
    try:
        return int(user.get("auth_version", 0)) == int(auth_version)
    except (TypeError, ValueError):
        return False


def login(email: str, password: str) -> dict:
    _, user = _find_owner(email)
    if not user or not check_password_hash(str(user.get("password_hash", "")), password or ""):
        return {"ok": False}
    return {
        "ok": True,
        "role": "owner",
        "email": user["email"],
        "auth_version": int(user.get("auth_version", 0)),
        "two_factor_required": bool(user.get("two_factor_enabled")),
    }


def verify_session(email: str, auth_version) -> dict:
    _, user = _find_owner(email)
    if not user or not _version_matches(user, auth_version):
        return {"ok": False}
    return {"ok": True, "role": "owner", "email": user["email"]}


def verify_second_factor(email: str, auth_version, code: str) -> dict:
    _, user = _find_owner(email)
    if not user or not _version_matches(user, auth_version):
        return {"ok": False}
    secret = user.get("totp_secret")
    if not secret or not user.get("two_factor_enabled"):
        return {"ok": False}
    if not pyotp.TOTP(secret).verify(str(code or ""), valid_window=1):
        return {"ok": False}
    return {"ok": True, "role": "owner", "email": user["email"], "auth_version": int(user["auth_version"])}


def two_factor_status(email: str, auth_version) -> dict:
    _, user = _find_owner(email)
    if not user or not _version_matches(user, auth_version):
        return {"ok": False}
    return {"ok": True, "data": {"enabled": bool(user.get("two_factor_enabled"))}}


def begin_two_factor(email: str, auth_version, current_password: str) -> dict:
    users, user = _find_owner(email)
    if not user or not _version_matches(user, auth_version):
        return {"ok": False}
    if not check_password_hash(str(user.get("password_hash", "")), current_password or ""):
        return {"ok": False}
    secret = pyotp.random_base32()
    user["totp_pending_secret"] = secret
    _save_users(users)
    uri = pyotp.TOTP(secret).provisioning_uri(name=user["email"], issuer_name=TOTP_ISSUER)
    return {"ok": True, "data": {"secret": secret, "otpauth_uri": uri}}


def confirm_two_factor(email: str, auth_version, code: str) -> dict:
    users, user = _find_owner(email)
    if not user or not _version_matches(user, auth_version):
        return {"ok": False}
    pending = user.get("totp_pending_secret")
    if not pending or not pyotp.TOTP(pending).verify(str(code or ""), valid_window=1):
        return {"ok": False}
    user["totp_secret"] = pending
    user.pop("totp_pending_secret", None)
    user["two_factor_enabled"] = True
    user["auth_version"] = int(user.get("auth_version", 0)) + 1
    _save_users(users)
    return {"ok": True}


def disable_two_factor(email: str, auth_version, current_password: str, code: str) -> dict:
    users, user = _find_owner(email)
    if not user or not _version_matches(user, auth_version):
        return {"ok": False}
    if not check_password_hash(str(user.get("password_hash", "")), current_password or ""):
        return {"ok": False}
    secret = user.get("totp_secret")
    if not secret or not pyotp.TOTP(secret).verify(str(code or ""), valid_window=1):
        return {"ok": False}
    user.pop("totp_secret", None)
    user["two_factor_enabled"] = False
    user["auth_version"] = int(user.get("auth_version", 0)) + 1
    _save_users(users)
    return {"ok": True}


def change_password(email: str, current_password: str, new_password: str) -> dict:
    users, user = _find_owner(email)
    if not user:
        return {"ok": False}
    if not check_password_hash(str(user.get("password_hash", "")), current_password or ""):
        return {"ok": False}
    if len(new_password or "") < MIN_PASSWORD_LENGTH:
        return {"ok": False, "error": f"New password must be at least {MIN_PASSWORD_LENGTH} characters"}
    user["password_hash"] = generate_password_hash(new_password, method="scrypt")
    user["auth_version"] = int(user.get("auth_version", 0)) + 1
    _save_users(users)
    return {"ok": True}


def password_reset_request(email: str) -> dict:
    # No SMS provider is wired up -- an honest failure instead of a fake
    # success that would leave the owner waiting for a code that never
    # arrives. The website keeps this path feature-flagged off
    # (CATALOGUE_STUDIO_PASSWORD_RESET_ENABLED=0) until it's real.
    return {"ok": False, "error": "Password reset is not configured (no SMS provider wired up yet)."}


def password_reset_confirm(*_args, **_kwargs) -> dict:
    return {"ok": False, "error": "Password reset is not configured (no SMS provider wired up yet)."}
