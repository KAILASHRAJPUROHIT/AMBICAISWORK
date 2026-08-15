"""Masked Windows setup dialog for catalogue email 2FA."""

from __future__ import annotations

import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from tkinter import Tk, messagebox, simpledialog


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from email_2fa import OTP_RECIPIENT, send_otp, store_app_password


STATUS_PATH = ROOT / "config" / "email_2fa_setup_status.json"


def record(ok: bool, message: str) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        json.dumps(
            {
                "ok": ok,
                "message": message,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    root = Tk()
    root.withdraw()
    value = simpledialog.askstring(
        "Catalogue email 2FA",
        "Paste the 16-character Google App Password.\nSpaces are accepted. Input is hidden.",
        show="*",
        parent=root,
    )
    if value is None:
        record(False, "Setup cancelled")
        return 1

    try:
        store_app_password(value)
        test_code = f"{secrets.randbelow(1_000_000):06d}"
        send_otp(test_code)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        record(False, message)
        messagebox.showerror("Email 2FA setup failed", message, parent=root)
        return 1

    message = f"Configured successfully. Test code sent to {OTP_RECIPIENT}."
    record(True, message)
    messagebox.showinfo("Email 2FA ready", message, parent=root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
