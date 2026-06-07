import argparse
import json
import os
import sys
from datetime import datetime
from decimal import Decimal

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database import Base, SessionLocal, engine
from backend.models import AuditLog, Bill, PaymentConfirmationSignature
from backend.payment_confirmation_signature import build_payment_confirmation_signature


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _print_signature(prefix: str, signature: dict):
    print(prefix)
    for key in (
        "bill_id",
        "invoice_no",
        "invoice_amount",
        "matched_amount",
        "difference_amount",
        "payment_mode",
        "payment_status",
        "confidence_level",
        "confidence_score",
        "confidence_reason",
        "proof_status",
        "proof_source",
        "proof_id",
        "proof_reference",
        "proof_timestamp",
        "proof_amount",
        "requires_accountant_review",
        "requires_owner_review",
        "verification_state",
        "signature_hash",
    ):
        print(f"  {key}: {signature.get(key)}")


def _upsert_signature(db, signature: dict):
    existing = (
        db.query(PaymentConfirmationSignature)
        .filter(PaymentConfirmationSignature.bill_id == signature["bill_id"])
        .first()
    )
    if existing and existing.signature_hash == signature["signature_hash"]:
        return "unchanged", existing

    action = "PAYMENT_SIGNATURE_CREATED" if existing is None else "PAYMENT_SIGNATURE_UPDATED"
    old_hash = existing.signature_hash if existing else None
    if existing is None:
        existing = PaymentConfirmationSignature()
        db.add(existing)

    for key, value in signature.items():
        setattr(existing, key, value)
    existing.updated_at = datetime.now()

    audit = AuditLog(
        entity_type="PaymentConfirmationSignature",
        entity_id=signature["bill_id"],
        action=action,
        old_status=old_hash,
        new_status=signature["signature_hash"],
        actor="SYSTEM",
        metadata_json=json.dumps(signature, default=_json_default, sort_keys=True),
    )
    db.add(audit)
    return "created" if action.endswith("CREATED") else "updated", existing


def run_backfill():
    parser = argparse.ArgumentParser(description="Backfill deterministic payment confirmation signatures.")
    parser.add_argument("--apply", action="store_true", help="Apply signature upserts to the database. Defaults to dry-run.")
    parser.add_argument("--invoice", help="Limit processing to one invoice number.")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{datetime.now()}] Starting Payment Confirmation Signature Backfill (Mode: {mode})")

    Base.metadata.create_all(bind=engine, tables=[PaymentConfirmationSignature.__table__])
    print("Table ensured: payment_confirmation_signatures")

    db = SessionLocal()
    summary = {
        "processed": 0,
        "updates_detected": 0,
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "errors": 0,
    }
    ss_534_signature = None
    try:
        query = db.query(Bill).filter(Bill.is_test_data == False)
        if args.invoice:
            query = query.filter(Bill.bill_number == args.invoice)
        bills = query.order_by(Bill.id.asc()).all()
        print(f"Found {len(bills)} bills to evaluate.")

        for bill in bills:
            summary["processed"] += 1
            try:
                signature = build_payment_confirmation_signature(db, bill.id)
                if signature["invoice_no"] == "SS-534":
                    ss_534_signature = signature
                existing = (
                    db.query(PaymentConfirmationSignature)
                    .filter(PaymentConfirmationSignature.bill_id == bill.id)
                    .first()
                )
                changed = existing is None or existing.signature_hash != signature["signature_hash"]
                if changed:
                    summary["updates_detected"] += 1
                    if args.apply:
                        result, _ = _upsert_signature(db, signature)
                        summary[result] += 1
                else:
                    summary["unchanged"] += 1
            except Exception as exc:
                summary["errors"] += 1
                print(f"ERROR invoice={bill.bill_number} bill_id={bill.id}: {exc}")

        if args.apply:
            db.commit()
            print("Changes committed to database.")
        else:
            db.rollback()
            print("DRY-RUN COMPLETE. No changes were made to the database.")
            if summary["updates_detected"]:
                print(f"Run with --apply to commit {summary['updates_detected']} signature updates.")

        print("\n--- Backfill Summary ---")
        for key in ("processed", "updates_detected", "created", "updated", "unchanged", "errors"):
            print(f"{key.replace('_', ' ').title():18}: {summary[key]}")

        if ss_534_signature:
            print("\n--- SS-534 Signature Preview ---")
            _print_signature("SS-534", ss_534_signature)
        else:
            print("\n--- SS-534 Signature Preview ---")
            print("SS-534 not found in evaluated bill set.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_backfill()
