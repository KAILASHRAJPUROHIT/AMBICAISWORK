# Standalone service for the Aradhana bank-activity notifier (the always-on-
# top desktop popup). Extracted from payment-auditor/backend/review_api.py —
# only the /api/bank-activity* routes and their direct dependencies. No
# Bill/Payment/Cheque/Prime/reconciliation code exists in this service at all.
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import AuditLog, SMSAlert, SystemSetting
from sms_parser import (
    detect_credit_or_debit,
    extract_account_display,
    extract_counterparty,
    extract_payment_mode,
    parse_bank_sms,
    parse_sms_body,
)
from email_poller import email_status, start_email_poller

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("payment-notifier")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Aradhana Payment Notifier")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

NOTIFIER_TOKEN = os.environ.get("NOTIFIER_TOKEN", "")
RELAY_TOKEN = os.environ.get("RELAY_TOKEN", "")


# --- Auth -------------------------------------------------------------
# Replaces the old LAN-only IP check (_require_lan_bank_activity), which
# can't work once this is public on AWS. Two separate shared tokens: one
# for the desktop notifier polling for alerts, one for the Android SMS
# relay pushing them in — so a leaked notifier token can't be used to
# inject fake transactions.
def require_notifier_token(x_notifier_token: str = Header(default="")):
    if not NOTIFIER_TOKEN or x_notifier_token != NOTIFIER_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing notifier token.")


def require_relay_token(x_relay_token: str = Header(default="")):
    if not RELAY_TOKEN or x_relay_token != RELAY_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing relay token.")


@app.on_event("startup")
def on_startup():
    if os.environ.get("NOTIFIER_ENABLE_EMAIL_POLL", "1") == "1":
        start_email_poller()
    else:
        logger.info("Email poller disabled via NOTIFIER_ENABLE_EMAIL_POLL=0")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def status_page():
    """Unauthenticated at-a-glance status - no bank data, just service health."""
    poller_state = "running" if email_status.get("is_running") is not None else "unknown"
    last_sync = email_status.get("last_sync") or "never yet"
    last_error = email_status.get("last_error")
    error_html = f'<p class="err">Last email-poll error: {last_error}</p>' if last_error else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Aradhana Payment Notifier</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; max-width: 640px; margin: 48px auto; padding: 0 16px; color: #10254A; }}
  h1 {{ color: #23519D; }}
  .ok {{ color: #146C43; font-weight: bold; }}
  .err {{ color: #B42332; }}
  code {{ background: #f3f3f3; padding: 2px 6px; border-radius: 4px; }}
  ul {{ line-height: 1.9; }}
</style></head>
<body>
<h1>Aradhana Payment Notifier</h1>
<p class="ok">&#9679; Service is up</p>
<p>Email poller: {poller_state} &mdash; last sync: {last_sync}</p>
{error_html}
<p>This backend feeds the bank-activity desktop popup and the Android SMS relay.
No transaction data is shown here &mdash; that requires the notifier token.</p>
<ul>
  <li><code>GET /api/health</code> &mdash; plain health check, no auth</li>
  <li><code>GET /api/bank-activity</code> &mdash; requires <code>X-Notifier-Token</code></li>
  <li><code>POST /api/sms-relay/ingest</code> &mdash; requires <code>X-Relay-Token</code></li>
</ul>
</body></html>"""


# --- Shared helpers (ported from review_api.py, unchanged behavior) ---
def _normalise_bank_activity_reference(reference: str) -> str:
    return re.sub(r"\s+", "", (reference or "").strip()).upper()


def _bank_activity_copy_key(reference: str) -> str:
    return f"bank_activity_copy_state:{hashlib.sha256(_normalise_bank_activity_reference(reference).encode('utf-8')).hexdigest()}"


def _bank_activity_copy_states(db: Session) -> Dict[str, int]:
    states: Dict[str, int] = {}
    for setting in db.query(SystemSetting).filter(SystemSetting.key.like("bank_activity_copy_state:%")).all():
        try:
            state = json.loads(setting.value)
            reference = _normalise_bank_activity_reference(str(state.get("reference", "")))
            count = max(0, int(state.get("count", 0)))
            if reference:
                states[reference] = count
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return states


def _bank_activity_copy_colour(count: int) -> str:
    return "red" if count >= 2 else "green" if count == 1 else "blue"


def _bank_activity_row(alert: SMSAlert, direction: str, duplicate: bool = False, correction: Optional[dict] = None, copy_counts: Optional[Dict[str, int]] = None) -> dict:
    """Sanitised live-view record. Deliberately never exposes the raw SMS body."""
    raw_body = alert.raw_body or ""
    parsed = parse_bank_sms(raw_body)
    account = extract_account_display(raw_body) or alert.account_suffix or parsed.account_suffix or "Not recorded"
    counterparty = extract_counterparty(raw_body, direction) or alert.payer_name or parsed.payer_name or "Not recorded"
    timestamp = alert.transaction_timestamp or alert.created_at
    row = {
        "id": alert.id,
        "bank_name": alert.bank_name or parsed.sender_bank or "Not recorded",
        "account": account,
        "counterparty": counterparty,
        "amount": float(alert.amount or 0),
        "date": timestamp.strftime("%d %b %Y") if timestamp else "Not recorded",
        "time": timestamp.strftime("%H:%M:%S") if timestamp else "Not recorded",
        "reference": alert.utr_reference or parsed.utr_reference or "Not recorded",
        "mode": extract_payment_mode(raw_body) or "Not recorded",
        "recorded_at": timestamp.isoformat() if timestamp else None,
        "flags": {
            "duplicate_reference": duplicate,
            "reversal_or_refund": bool(re.search(r"\b(revers(?:ed|al)?|refund|chargeback)\b", raw_body, re.IGNORECASE)),
        },
        "is_corrected": bool(correction),
    }
    for key in ("bank_name", "account", "counterparty", "reference", "mode"):
        value = (correction or {}).get(key)
        if isinstance(value, str) and value.strip():
            row[key] = value.strip()
    copy_count = (copy_counts or {}).get(_normalise_bank_activity_reference(row["reference"]), 0)
    row["copy_count"] = copy_count
    row["copy_state"] = _bank_activity_copy_colour(copy_count)
    return row


def _activity_corrections(db: Session) -> Dict[int, dict]:
    corrections = {}
    for setting in db.query(SystemSetting).filter(SystemSetting.key.like("bank_activity_correction:%")).all():
        try:
            corrections[int(setting.key.rsplit(":", 1)[1])] = json.loads(setting.value)
        except (ValueError, json.JSONDecodeError):
            continue
    return corrections


def _active_bank_activity_test_popups(db: Session) -> List[dict]:
    now = datetime.now()
    active = []
    for setting in db.query(SystemSetting).filter(SystemSetting.key.like("bank_activity_test_popup:%")).all():
        try:
            notice = json.loads(setting.value)
            if datetime.fromisoformat(notice["expires_at"]) > now:
                active.append(notice["alert"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return active


# --- Routes (same shapes the existing notifier/dashboard clients expect) ---
@app.get("/api/bank-activity")
async def get_bank_activity(request: Request, db: Session = Depends(get_db), _auth=Depends(require_notifier_token)):
    """Latest credited/debited bank SMS records for the notifier popup."""
    history_start = datetime.now() - timedelta(days=30)
    alerts = (
        db.query(SMSAlert)
        .filter(SMSAlert.transaction_timestamp >= history_start)
        .order_by(SMSAlert.transaction_timestamp.desc())
        .limit(500)
        .all()
    )
    reference_counts: Dict[str, int] = {}
    for alert in alerts:
        if alert.utr_reference:
            reference_counts[alert.utr_reference] = reference_counts.get(alert.utr_reference, 0) + 1
    corrections = _activity_corrections(db)
    copy_counts = _bank_activity_copy_states(db)
    credits, debits = [], []
    for alert in alerts:
        direction = detect_credit_or_debit(alert.raw_body) or (alert.credit_or_debit or "").upper()
        if direction == "CREDIT":
            credits.append(_bank_activity_row(alert, direction, reference_counts.get(alert.utr_reference or "", 0) > 1, corrections.get(alert.id), copy_counts))
        elif direction == "DEBIT":
            debits.append(_bank_activity_row(alert, direction, reference_counts.get(alert.utr_reference or "", 0) > 1, corrections.get(alert.id), copy_counts))
    latest = max((alert.transaction_timestamp for alert in alerts if alert.transaction_timestamp), default=None)
    return {
        "generated_at": datetime.now().isoformat(),
        "history_start": history_start.isoformat(),
        "credits": credits,
        "debits": debits,
        "test_alerts": _active_bank_activity_test_popups(db),
        "health": {
            "last_relay_transaction_at": latest.isoformat() if latest else None,
            "last_email_sync": email_status.get("last_sync"),
            "email_sync_running": bool(email_status.get("is_running")),
            "email_error": email_status.get("last_error"),
        },
    }


@app.post("/api/bank-activity/test-popup")
async def send_bank_activity_test_popup(db: Session = Depends(get_db), _auth=Depends(require_notifier_token)):
    """Send a harmless test popup to every enabled notifier for one minute."""
    test_id = f"test-{uuid4().hex}"
    alert = {
        "id": test_id,
        "direction": "CREDIT",
        "bank_name": "ARADHANA TEST",
        "account": "TEST ONLY",
        "counterparty": "Popup verification",
        "amount": 1.00,
        "date": datetime.now().strftime("%d %b %Y"),
        "time": datetime.now().strftime("%H:%M:%S"),
        "reference": "TEST-POPUP-001",
        "mode": "TEST",
        "recorded_at": datetime.now().isoformat(),
        "flags": {"duplicate_reference": False, "reversal_or_refund": False},
        "is_corrected": False,
        "copy_count": 0,
        "copy_state": "blue",
    }
    db.add(SystemSetting(
        key=f"bank_activity_test_popup:{test_id}",
        value=json.dumps({"expires_at": (datetime.now() + timedelta(seconds=60)).isoformat(), "alert": alert}),
    ))
    db.add(AuditLog(entity_type="BankActivity", entity_id=0, action="TEST_POPUP_SENT", actor="NOTIFIER_API", metadata_json=json.dumps({"test_id": test_id})))
    db.commit()
    return {"status": "sent", "test_id": test_id, "expires_in_seconds": 60}


class BankActivityCorrectionInput(BaseModel):
    bank_name: Optional[str] = None
    account: Optional[str] = None
    counterparty: Optional[str] = None
    reference: Optional[str] = None
    mode: Optional[str] = None
    note: Optional[str] = None


class BankActivityReferenceCopiedInput(BaseModel):
    reference: str
    source: str = "dashboard"


@app.post("/api/bank-activity/reference-copied")
async def record_bank_activity_reference_copy(payload: BankActivityReferenceCopiedInput, request: Request, db: Session = Depends(get_db), _auth=Depends(require_notifier_token)):
    reference = _normalise_bank_activity_reference(payload.reference)
    if not reference or reference == "NOTRECORDED" or len(reference) > 160:
        raise HTTPException(status_code=400, detail="A valid Ref / UTR is required.")
    source = (payload.source or "dashboard").strip().lower()[:40]
    key = _bank_activity_copy_key(reference)
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    previous_count = 0
    if setting:
        try:
            previous_count = max(0, int(json.loads(setting.value).get("count", 0)))
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            previous_count = 0
    count = previous_count + 1
    state = {"reference": reference, "count": count, "first_copied_at": datetime.now().isoformat() if previous_count == 0 else None, "last_copied_at": datetime.now().isoformat()}
    if setting:
        setting.value = json.dumps(state)
    else:
        db.add(SystemSetting(key=key, value=json.dumps(state)))
    db.add(AuditLog(
        entity_type="BankActivityReference",
        entity_id=0,
        action="REFERENCE_COPIED",
        actor="NOTIFIER_API",
        metadata_json=json.dumps({"reference": reference, "copy_count": count, "source": source, "client_ip": request.client.host if request.client else None}),
    ))
    db.commit()
    return {"reference": reference, "copy_count": count, "copy_state": _bank_activity_copy_colour(count)}


@app.post("/api/bank-activity/{alert_id}/correction")
async def correct_bank_activity(alert_id: int, correction: BankActivityCorrectionInput, db: Session = Depends(get_db), _auth=Depends(require_notifier_token)):
    alert = db.query(SMSAlert).filter(SMSAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Bank activity record not found.")
    values = {key: (getattr(correction, key) or "").strip() for key in ("bank_name", "account", "counterparty", "reference", "mode")}
    values = {key: value[:160] for key, value in values.items() if value}
    if not values:
        raise HTTPException(status_code=400, detail="Enter at least one corrected value.")
    values["note"] = (correction.note or "").strip()[:500]
    key = f"bank_activity_correction:{alert_id}"
    previous_setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    previous = previous_setting.value if previous_setting else None
    if previous_setting:
        previous_setting.value = json.dumps(values)
    else:
        db.add(SystemSetting(key=key, value=json.dumps(values)))
    db.add(AuditLog(
        entity_type="BankActivity",
        entity_id=alert_id,
        action="DISPLAY_CORRECTION",
        old_status=previous,
        new_status=json.dumps(values),
        actor="NOTIFIER_API",
        metadata_json=json.dumps({"source": "BankActivityAPI", "note": values["note"], "timestamp": datetime.now().isoformat()}),
    ))
    db.commit()
    return {"status": "saved", "alert_id": alert_id}


# --- SMS relay ingest (new) --------------------------------------------
# Replaces the old file-drop poller (sms_poller.py watching a Windows
# network share, Z:\Aradhana\SMSInbox), which can't exist on AWS. The
# Android relay app now POSTs the same shape directly instead of writing
# a JSON file for a poller to pick up later.
class SmsRelayIngestInput(BaseModel):
    sms_id: Optional[str] = None
    sender: str
    body: str
    timestamp: str  # ISO 8601


@app.post("/api/sms-relay/ingest")
async def ingest_relayed_sms(payload: SmsRelayIngestInput, db: Session = Depends(get_db), _auth=Depends(require_relay_token)):
    parsed_data = parse_sms_body(payload.body)
    if parsed_data["credit_or_debit"] != "CREDIT" or parsed_data["amount"] <= 0:
        return {"status": "skipped", "reason": "not a positive credit"}

    try:
        received_at = datetime.fromisoformat(payload.timestamp)
    except ValueError:
        raise HTTPException(status_code=400, detail="timestamp must be ISO 8601.")

    exists = None
    if payload.sms_id:
        exists = db.query(SMSAlert).filter(SMSAlert.sms_id == payload.sms_id).first()
    if not exists and parsed_data["utr_reference"]:
        exists = db.query(SMSAlert).filter(SMSAlert.utr_reference == parsed_data["utr_reference"]).first()
    if exists:
        return {"status": "duplicate", "id": exists.id}

    new_sms = SMSAlert(
        sms_id=payload.sms_id,
        sender=payload.sender,
        transaction_timestamp=received_at,
        bank_name=parsed_data["bank_name"],
        account_suffix=parsed_data["account_suffix"],
        credit_or_debit=parsed_data["credit_or_debit"],
        amount=parsed_data["amount"],
        utr_reference=parsed_data["utr_reference"],
        payer_name=parsed_data["payer_name"],
        raw_body=payload.body,
        parsed_confidence=1.0 if parsed_data["confidence"] == "HIGH" else 0.5,
    )
    db.add(new_sms)
    db.commit()
    db.refresh(new_sms)
    logger.info(f"Ingested relayed SMS: id={new_sms.id} utr={new_sms.utr_reference}")
    return {"status": "stored", "id": new_sms.id}
