import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.database import Base, SessionLocal, engine
from backend.models import AuditLog, Bill, PaymentConfirmationSignature
from backend.payment_confirmation_signature import build_payment_confirmation_signature

logger = logging.getLogger("PaymentSignatureScheduler")

TODAY_INTERVAL_SECONDS = 15
HISTORICAL_INTERVAL_SECONDS = 3600
LOOKBACK_DAYS = 30
CLOSED_SIGNATURE_STATES = {"ACCOUNTANT_VERIFIED", "OWNER_APPROVED", "CLOSED"}
CLOSED_BILL_STATUSES = {"ARCHIVED", "CLOSED", "GREY", "GRAY"}

_scheduler_thread_started = False
_scheduler_lock = threading.Lock()


def _int_env(name: str, default: int, minimum: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        logger.warning(f"Invalid {name}={raw_value!r}; defaulting to {default}.")
        value = default
    return max(value, minimum)


def _bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def get_scheduler_config() -> dict:
    return {
        "enabled": _bool_env("SIGNATURE_SCHEDULER_ENABLED", False),
        "dry_run": _bool_env("SIGNATURE_SCHEDULER_DRY_RUN", False),
        "today_interval_seconds": _int_env("TODAY_SIGNATURE_REBUILD_INTERVAL_SECONDS", TODAY_INTERVAL_SECONDS, 5),
        "historical_interval_seconds": _int_env("HISTORICAL_SIGNATURE_REBUILD_INTERVAL_SECONDS", HISTORICAL_INTERVAL_SECONDS, 60),
        "lookback_days": _int_env("SIGNATURE_REBUILD_LOOKBACK_DAYS", LOOKBACK_DAYS, 1),
    }


def ensure_signature_table():
    Base.metadata.create_all(bind=engine, tables=[PaymentConfirmationSignature.__table__])


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _is_closed_bill(bill: Bill) -> bool:
    return (bill.status or "").upper() in CLOSED_BILL_STATUSES


def _is_closed_signature(signature: PaymentConfirmationSignature | None) -> bool:
    if not signature:
        return False
    return (signature.verification_state or "").upper() in CLOSED_SIGNATURE_STATES


def _qualifying_today_bills(db: Session, now: datetime) -> list[Bill]:
    today = now.date().isoformat()
    return (
        db.query(Bill)
        .filter(
            Bill.is_test_data == False,  # noqa: E712
            func.date(Bill.invoice_date) == today,
        )
        .order_by(Bill.id.asc())
        .all()
    )


def _qualifying_historical_bills(db: Session, now: datetime, lookback_days: int) -> list[Bill]:
    today = now.date()
    start_date = today - timedelta(days=lookback_days)
    yesterday = today - timedelta(days=1)
    return (
        db.query(Bill)
        .filter(
            Bill.is_test_data == False,  # noqa: E712
            func.date(Bill.invoice_date) >= start_date.isoformat(),
            func.date(Bill.invoice_date) <= yesterday.isoformat(),
            Bill.status != "Green",
        )
        .order_by(Bill.invoice_date.desc().nullslast(), Bill.id.asc())
        .all()
    )


def _existing_signature(db: Session, bill_id: int) -> PaymentConfirmationSignature | None:
    return (
        db.query(PaymentConfirmationSignature)
        .filter(PaymentConfirmationSignature.bill_id == bill_id)
        .first()
    )


def _upsert_signature(db: Session, signature: dict) -> str:
    existing = _existing_signature(db, signature["bill_id"])
    if existing and existing.signature_hash == signature["signature_hash"]:
        return "unchanged"

    action = "PAYMENT_SIGNATURE_CREATED" if existing is None else "PAYMENT_SIGNATURE_UPDATED"
    old_hash = existing.signature_hash if existing else None
    if existing is None:
        existing = PaymentConfirmationSignature()
        db.add(existing)

    for key, value in signature.items():
        setattr(existing, key, value)
    existing.updated_at = datetime.now()

    db.add(AuditLog(
        entity_type="PaymentConfirmationSignature",
        entity_id=signature["bill_id"],
        action=action,
        old_status=old_hash,
        new_status=signature["signature_hash"],
        actor="SYSTEM_SIGNATURE_SCHEDULER",
        metadata_json=json.dumps(signature, default=_json_default, sort_keys=True),
    ))
    return "created" if action.endswith("CREATED") else "updated"


def _process_bills(db: Session, bills: list[Bill], dry_run: bool) -> dict:
    summary = {
        "evaluated": 0,
        "skipped_closed": 0,
        "changed": 0,
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "errors": 0,
        "ss_534": None,
    }
    for bill in bills:
        existing = _existing_signature(db, bill.id)
        if _is_closed_bill(bill) or _is_closed_signature(existing):
            summary["skipped_closed"] += 1
            continue

        summary["evaluated"] += 1
        try:
            signature = build_payment_confirmation_signature(db, bill.id)
            if signature["invoice_no"] == "SS-534":
                summary["ss_534"] = signature
            changed = existing is None or existing.signature_hash != signature["signature_hash"]
            if not changed:
                summary["unchanged"] += 1
                continue

            summary["changed"] += 1
            if dry_run:
                continue

            result = _upsert_signature(db, signature)
            summary[result] += 1
        except Exception as exc:
            summary["errors"] += 1
            logger.error(f"Signature rebuild failed for bill_id={bill.id} invoice={bill.bill_number}: {exc}")
    return summary


def run_signature_rebuild_once(scope: str = "today", dry_run: bool = True, now: datetime | None = None) -> dict:
    ensure_signature_table()
    config = get_scheduler_config()
    now = now or datetime.now()
    db = SessionLocal()
    try:
        if scope == "today":
            bills = _qualifying_today_bills(db, now)
        elif scope == "historical":
            bills = _qualifying_historical_bills(db, now, config["lookback_days"])
        else:
            raise ValueError(f"Unknown signature rebuild scope: {scope}")

        summary = _process_bills(db, bills, dry_run=dry_run)
        summary["scope"] = scope
        summary["dry_run"] = dry_run
        summary["candidate_count"] = len(bills)
        if dry_run:
            db.rollback()
        else:
            db.commit()
        return summary
    except OperationalError as exc:
        db.rollback()
        logger.error(f"Signature rebuild DB error ({scope}): {exc}")
        return {"scope": scope, "dry_run": dry_run, "db_error": str(exc)}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _scheduler_loop():
    config = get_scheduler_config()
    dry_run = config["dry_run"]
    today_interval = config["today_interval_seconds"]
    historical_interval = config["historical_interval_seconds"]
    logger.info(
        f"Payment signature scheduler started. today_interval={today_interval}s, "
        f"historical_interval={historical_interval}s, dry_run={dry_run}"
    )
    next_historical_at = 0.0
    while True:
        try:
            logger.info(f"Today signature rebuild summary: {run_signature_rebuild_once('today', dry_run=dry_run)}")
            now_ts = time.time()
            if now_ts >= next_historical_at:
                logger.info(f"Historical signature rebuild summary: {run_signature_rebuild_once('historical', dry_run=dry_run)}")
                next_historical_at = now_ts + historical_interval
        except Exception as exc:
            logger.error(f"Payment signature scheduler loop error: {exc}")
        time.sleep(today_interval)


def start_payment_signature_scheduler():
    global _scheduler_thread_started
    config = get_scheduler_config()
    if not config["enabled"]:
        logger.info("Payment signature scheduler disabled by SIGNATURE_SCHEDULER_ENABLED.")
        return False

    ensure_signature_table()
    with _scheduler_lock:
        if _scheduler_thread_started:
            logger.info("Payment signature scheduler already running.")
            return True
        thread = threading.Thread(target=_scheduler_loop, daemon=True)
        thread.start()
        _scheduler_thread_started = True
        return True
