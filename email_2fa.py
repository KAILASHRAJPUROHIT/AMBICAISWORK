"""Local DPAPI-protected Google Workspace SMTP support for catalogue 2FA."""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

import win32crypt
import win32cryptcon


BASE = Path(__file__).resolve().parent
SECRET_PATH = BASE / "config" / "email_2fa_smtp.dpapi"
SMTP_HOST = os.environ.get("AMBIC_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("AMBIC_SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("AMBIC_SMTP_USERNAME", "")


def _otp_recipient() -> str:
    """OTP destination: env var wins; else a persisted override under
    data/ (gitignored, same convention as _generated_password() in
    app.py); else empty, meaning 2FA is not configured yet."""
    env_value = os.environ.get("AMBIC_OTP_RECIPIENT")
    if env_value:
        return env_value
    override_path = BASE / "data" / "otp_recipient.txt"
    if override_path.is_file():
        value = override_path.read_text(encoding="utf-8").strip()
        if value:
            return value
    return ""


OTP_RECIPIENT = _otp_recipient()


def configured() -> bool:
    has_credential = bool(os.environ.get("AMBIC_SMTP_APP_PASSWORD")) or SECRET_PATH.is_file()
    return has_credential and bool(SMTP_USERNAME) and bool(OTP_RECIPIENT)


def store_app_password(app_password: str) -> None:
    value = app_password.replace(" ", "").strip()
    if len(value) < 12:
        raise ValueError("Google app password is too short")
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    protected = win32crypt.CryptProtectData(
        value.encode("utf-8"),
        "AMBIC Catalogue email 2FA",
        None,
        None,
        None,
        win32cryptcon.CRYPTPROTECT_LOCAL_MACHINE,
    )
    SECRET_PATH.write_bytes(protected)


def _app_password() -> str:
    environment_value = os.environ.get("AMBIC_SMTP_APP_PASSWORD")
    if environment_value:
        return environment_value.replace(" ", "").strip()
    if not SECRET_PATH.is_file():
        raise RuntimeError("Email 2FA SMTP credential is not configured")
    clear = win32crypt.CryptUnprotectData(SECRET_PATH.read_bytes(), None, None, None, 0)[1]
    return clear.decode("utf-8")


def send_otp(code: str) -> None:
    message = EmailMessage()
    message["Subject"] = f"AMBIC Catalogue sign-in code: {code}"
    message["From"] = SMTP_USERNAME
    message["To"] = OTP_RECIPIENT
    message.set_content(
        "A sign-in was requested for AMBIC Catalogue Studio.\n\n"
        f"Verification code: {code}\n\n"
        "This code expires in 10 minutes. If this was not you, do not share the code."
    )

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(SMTP_USERNAME, _app_password())
        smtp.send_message(message)
