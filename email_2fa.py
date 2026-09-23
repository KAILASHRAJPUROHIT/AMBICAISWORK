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
SMTP_HOST = os.environ.get("ARADHANA_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("ARADHANA_SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("ARADHANA_SMTP_USERNAME", "info@aradhanajewellers.com")
OTP_RECIPIENT = os.environ.get("ARADHANA_OTP_RECIPIENT", "info@aradhanajewellers.com")


def configured() -> bool:
    return bool(os.environ.get("ARADHANA_SMTP_APP_PASSWORD")) or SECRET_PATH.is_file()


def store_app_password(app_password: str) -> None:
    value = app_password.replace(" ", "").strip()
    if len(value) < 12:
        raise ValueError("Google app password is too short")
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    protected = win32crypt.CryptProtectData(
        value.encode("utf-8"),
        "Aradhana Catalogue email 2FA",
        None,
        None,
        None,
        win32cryptcon.CRYPTPROTECT_LOCAL_MACHINE,
    )
    SECRET_PATH.write_bytes(protected)


def _app_password() -> str:
    environment_value = os.environ.get("ARADHANA_SMTP_APP_PASSWORD")
    if environment_value:
        return environment_value.replace(" ", "").strip()
    if not SECRET_PATH.is_file():
        raise RuntimeError("Email 2FA SMTP credential is not configured")
    clear = win32crypt.CryptUnprotectData(SECRET_PATH.read_bytes(), None, None, None, 0)[1]
    return clear.decode("utf-8")


def send_otp(code: str) -> None:
    message = EmailMessage()
    message["Subject"] = f"Aradhana Catalogue sign-in code: {code}"
    message["From"] = SMTP_USERNAME
    message["To"] = OTP_RECIPIENT
    message.set_content(
        "A sign-in was requested for Aradhana Catalogue Studio.\n\n"
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
