import os
import time
import logging
import threading
import re
import hashlib
from datetime import datetime
from sqlalchemy.orm import Session
from backend.database import get_session_factory
from backend import business_registry
from backend.models import SMSAlert, BankAlert, Bill, AuditLog, Payment
from backend.sms_parser import parse_sms_body
import json

logger = logging.getLogger("SMS_Poller")

# Per-tenant status trackers — see pdf_ingestion.py's equivalent comment.
_sms_status: dict[str, dict] = {}

# Was hardcoded to Z:\Aradhana\SMSInbox — one specific business's own
# mapped drive. SMS_INBOX_PATH env var lets a deployment point at its own
# real location; the default here is business-neutral and simply won't
# exist until configured (os.path.exists guard below already handles that
# gracefully — this poller no-ops rather than errors with nothing mounted).
SMS_INBOX_PATH = os.environ.get("SMS_INBOX_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sms_inbox"))
status_lock = threading.Lock()


def _sms_status_for(slug: str) -> dict:
    with status_lock:
        if slug not in _sms_status:
            _sms_status[slug] = {
                "last_sync": None,
                "next_sync": None,
                "events_found": 0,
                "last_error": None,
                "is_running": False,
            }
        return _sms_status[slug]


def update_sms_status(slug: str, **kwargs):
    st = _sms_status_for(slug)
    with status_lock:
        for key, value in kwargs.items():
            if key in st:
                st[key] = value


def _tenant_sms_inbox_path(slug: str) -> str:
    profile = business_registry.load_profile(slug)
    return (profile or {}).get("sms_inbox_path") or SMS_INBOX_PATH

def get_event_fingerprint(bank, amount, utr, received_at, direction="CREDIT"):
    # bank + amount + utr/reference + date + direction
    date_str = received_at.strftime("%Y-%m-%d")
    raw = f"{bank}|{amount:.2f}|{utr}|{date_str}|{direction}"
    return hashlib.sha256(raw.encode()).hexdigest()

def process_sms(slug: str):
    """
    Android SMS collection with multi-point verification and cross-source deduplication.
    """
    logger.info(f"[{slug}] Polling Android SMS...")
    update_sms_status(slug, is_running=True)

    db = get_session_factory(slug)()
    events_found = 0
    try:
        sms_inbox_path = _tenant_sms_inbox_path(slug)
        source_sms = []
        if os.path.exists(sms_inbox_path):
            for filename in os.listdir(sms_inbox_path):
                if filename.endswith(".json"):
                    try:
                        with open(os.path.join(sms_inbox_path, filename), "r") as f:
                            data = json.load(f)
                            source_sms.append(data)
                    except: pass
        # No simulation fallback: an unconfigured SMS inbox used to
        # silently fabricate a fake ₹800 "successful" payment and insert it
        # into this business's real audit trail — a financial-integrity bug,
        # not a demo convenience worth keeping. An unconfigured inbox is now
        # exactly what it looks like: nothing to process this cycle.

        for sms in source_sms:
            raw_body = sms["body"]
            parsed_data = parse_sms_body(raw_body)
            
            # Skip non-credit or zero amount
            if parsed_data["credit_or_debit"] != "CREDIT" or parsed_data["amount"] <= 0:
                continue
                
            received_at = datetime.fromisoformat(sms["timestamp"])
            
            # Check for existing by sms_id or utr
            exists = db.query(SMSAlert).filter(SMSAlert.sms_id == sms.get("sms_id")).first()
            if not exists and parsed_data["utr_reference"]:
                 exists = db.query(SMSAlert).filter(SMSAlert.utr_reference == parsed_data["utr_reference"]).first()
            
            if not exists:
                new_sms = SMSAlert(
                    sms_id=sms.get("sms_id"),
                    sender=sms["sender"],
                    received_at=received_at,
                    bank_name=parsed_data["bank_name"],
                    account_suffix=parsed_data["account_suffix"],
                    credit_or_debit=parsed_data["credit_or_debit"],
                    amount=parsed_data["amount"],
                    utr_reference=parsed_data["utr_reference"],
                    raw_body=raw_body,
                    parsed_confidence=parsed_data["parsed_confidence"]
                )
                db.add(new_sms)
                events_found += 1
                
                # Cross-Verification / Deduplication with Email
                bank_alert = None
                if parsed_data["utr_reference"]:
                    bank_alert = db.query(BankAlert).filter(BankAlert.utr_reference == parsed_data["utr_reference"]).first()
                
                if not bank_alert:
                    # Create a consolidated BankAlert from SMS if it doesn't exist
                    bank_alert = BankAlert(
                        bank_name=parsed_data["bank_name"],
                        amount=parsed_data["amount"],
                        utr_reference=parsed_data["utr_reference"],
                        sender=sms["sender"],
                        received_at=received_at,
                        raw_text=f"SMS: {raw_body}"
                    )
                    db.add(bank_alert)
                    db.flush() 
                
                # RECONCILIATION LOGIC
                from backend.reconciliation.logic import verify_payment_event
                verify_payment_event(db, bank_alert, source="SMS")

        db.commit()
        update_sms_status(
            slug,
            last_sync=datetime.now().isoformat(),
            next_sync=(datetime.now().timestamp() + 1800),
            events_found=events_found
        )
    except Exception as e:
        db.rollback()
        logger.error(f"[{slug}] SMS Polling Error: {e}")
        update_sms_status(slug, last_error=str(e))
    finally:
        db.close()
        update_sms_status(slug, is_running=False)

def start_sms_poller():
    """One polling loop thread PER registered business — see
    pdf_ingestion.py's start_ingestion_thread for the same pattern and its
    limitations (new tenants need a restart to pick up polling)."""
    def run(slug):
        while True:
            process_sms(slug)
            time.sleep(1800)  # 30 minutes

    for slug in business_registry.list_businesses():
        thread = threading.Thread(target=run, args=(slug,), daemon=True)
        thread.start()
        logger.info(f"[{slug}] SMS poller thread started.")
