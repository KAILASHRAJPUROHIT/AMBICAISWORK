import argparse
import json
import os
import sys
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import or_  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from backend.database import Base, SessionLocal, engine  # noqa: E402
from backend.models import (  # noqa: E402
    AccountantVerificationQueue,
    AuditLog,
    Bill,
    PaymentConfirmationSignature,
)
from backend.payment_confirmation_signature import build_payment_confirmation_signature  # noqa: E402

OPEN_QUEUE_STATUSES = {"OPEN", "FURTHER_REVIEW", "OWNER_ESCALATION_PENDING"}
EXCLUDED_PREFIXES = ("TEST-", "ARCH-", "HARDENING-")


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def ensure_queue_table() -> None:
    Base.metadata.create_all(bind=engine, tables=[AccountantVerificationQueue.__table__])


def is_operational_bill(bill: Bill) -> bool:
    bill_number = (bill.bill_number or "").upper()
    return not (
        bill.is_test_data
        or any(bill_number.startswith(prefix) for prefix in EXCLUDED_PREFIXES)
    )


def queue_candidate_query(db: Session):
    return (
        db.query(Bill)
        .filter(
            Bill.is_test_data == False,  # noqa: E712
            ~Bill.bill_number.ilike("TEST-%"),
            ~Bill.bill_number.ilike("ARCH-%"),
            ~Bill.bill_number.ilike("HARDENING-%"),
            or_(Bill.status != "Green", Bill.review_required == 1),
        )
        .order_by(Bill.invoice_date.desc().nullslast(), Bill.id.asc())
    )


def active_queue_item(db: Session, bill_id: int) -> Optional[AccountantVerificationQueue]:
    return (
        db.query(AccountantVerificationQueue)
        .filter(
            AccountantVerificationQueue.bill_id == bill_id,
            AccountantVerificationQueue.queue_status.in_(OPEN_QUEUE_STATUSES),
        )
        .first()
    )


def signature_for_bill(db: Session, bill: Bill) -> tuple[Optional[PaymentConfirmationSignature], Dict[str, Any], str]:
    persisted = (
        db.query(PaymentConfirmationSignature)
        .filter(PaymentConfirmationSignature.bill_id == bill.id)
        .first()
    )
    if persisted:
        return persisted, {
            "payment_status": persisted.payment_status,
            "confidence_level": persisted.confidence_level,
            "proof_status": persisted.proof_status,
            "requires_accountant_review": persisted.requires_accountant_review,
            "verification_state": persisted.verification_state,
            "confidence_reason": persisted.confidence_reason,
        }, "persisted_signature"

    preview = build_payment_confirmation_signature(db, bill.id)
    return None, preview, "derived_preview"


def due_window(now: datetime) -> tuple[datetime, datetime]:
    verification_day = datetime.combine(now.date(), time(hour=10))
    if now < verification_day:
        verification_day = verification_day - timedelta(days=1)
    return verification_day, verification_day + timedelta(hours=48)


def build_queue_payload(db: Session, bill: Bill, now: datetime) -> Dict[str, Any]:
    persisted_signature, signature, signature_source = signature_for_bill(db, bill)
    verification_day, due_at = due_window(now)
    reason = signature.get("confidence_reason") or "Non-Green or review-required invoice requires accountant verification."
    return {
        "bill_id": bill.id,
        "payment_id": None,
        "signature_id": persisted_signature.id if persisted_signature else None,
        "invoice_no": bill.bill_number,
        "queue_status": "OPEN",
        "verification_day": verification_day,
        "due_at": due_at,
        "deferred_until": None,
        "owner_alert_after": None,
        "reason": reason,
        "proof_status": signature.get("proof_status"),
        "payment_status": signature.get("payment_status"),
        "confidence_level": signature.get("confidence_level"),
        "assigned_role": "ACCOUNTANT",
        "created_by": "SYSTEM_BACKFILL",
        "signature_source": signature_source,
        "bill_status": bill.status,
        "review_required": bill.review_required,
    }


def run_backfill(db: Session, apply: bool = False, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now()
    bills = [bill for bill in queue_candidate_query(db).all() if is_operational_bill(bill)]
    summary: Dict[str, Any] = {
        "mode": "APPLY" if apply else "DRY_RUN",
        "candidates": len(bills),
        "would_create": 0,
        "created": 0,
        "skipped_existing": 0,
        "rows": [],
    }

    for bill in bills:
        if active_queue_item(db, bill.id):
            summary["skipped_existing"] += 1
            continue

        payload = build_queue_payload(db, bill, now)
        row_summary = {
            "bill_id": payload["bill_id"],
            "invoice_no": payload["invoice_no"],
            "bill_status": payload["bill_status"],
            "review_required": payload["review_required"],
            "payment_status": payload["payment_status"],
            "confidence_level": payload["confidence_level"],
            "proof_status": payload["proof_status"],
            "signature_source": payload["signature_source"],
            "due_at": payload["due_at"].isoformat(),
        }
        summary["rows"].append(row_summary)

        if not apply:
            summary["would_create"] += 1
            continue

        queue_item = AccountantVerificationQueue(
            bill_id=payload["bill_id"],
            payment_id=payload["payment_id"],
            signature_id=payload["signature_id"],
            invoice_no=payload["invoice_no"],
            queue_status=payload["queue_status"],
            verification_day=payload["verification_day"],
            due_at=payload["due_at"],
            deferred_until=payload["deferred_until"],
            owner_alert_after=payload["owner_alert_after"],
            reason=payload["reason"],
            proof_status=payload["proof_status"],
            payment_status=payload["payment_status"],
            confidence_level=payload["confidence_level"],
            assigned_role=payload["assigned_role"],
            created_by=payload["created_by"],
        )
        db.add(queue_item)
        db.flush()
        db.add(AuditLog(
            entity_type="AccountantVerificationQueue",
            entity_id=queue_item.id,
            action="ACCOUNTANT_VERIFICATION_QUEUED",
            old_status=None,
            new_status=queue_item.queue_status,
            actor="SYSTEM_BACKFILL",
            metadata_json=json.dumps(row_summary, default=_json_default, sort_keys=True),
        ))
        summary["created"] += 1

    if apply:
        db.commit()
    else:
        db.rollback()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill accountant verification queue.")
    parser.add_argument("--apply", action="store_true", help="Write queue rows and audit logs. Default is dry-run.")
    args = parser.parse_args()

    ensure_queue_table()
    db = SessionLocal()
    try:
        summary = run_backfill(db, apply=args.apply)
        print(f"Mode: {summary['mode']}")
        print(f"Candidates: {summary['candidates']}")
        print(f"Would Create: {summary['would_create']}")
        print(f"Created: {summary['created']}")
        print(f"Skipped Existing: {summary['skipped_existing']}")
        print("Sample Rows:")
        for row in summary["rows"][:10]:
            print(json.dumps(row, default=_json_default, sort_keys=True))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
