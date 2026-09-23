"""Configure and test the DPAPI-protected Google Workspace SMTP credential."""

from __future__ import annotations

import getpass
import secrets
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from email_2fa import OTP_RECIPIENT, SMTP_USERNAME, send_otp, store_app_password


def main() -> int:
    print(f"Sender:    {SMTP_USERNAME}")
    print(f"Recipient: {OTP_RECIPIENT}")
    print("Enter the 16-character Google App Password. Input is hidden.")
    app_password = getpass.getpass("App password: ")
    store_app_password(app_password)
    test_code = f"{secrets.randbelow(1_000_000):06d}"
    send_otp(test_code)
    print(f"Email 2FA configured. Test code sent to {OTP_RECIPIENT}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
