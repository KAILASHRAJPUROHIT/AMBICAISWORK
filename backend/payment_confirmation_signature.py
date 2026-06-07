import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.models import BankAlert, Bill, Payment, SMSAlert

SIGNATURE_VERSION = "PCS_V1"

ELECTRONIC_MODES = {"UPI", "IMPS", "NEFT", "RTGS", "RTGS_OR_CHEQUE", "CARD", "BANK_TRANSFER"}
SPECIAL_REVIEW_TOKENS = (
    "ADVANCE",
    "OLD_GOLD_EXCHANGE",
    "OLD GOLD",
    "CUSTOMER PURCHASE",
    "CUST PURCHASE",
    "BUYBACK",
)


@dataclass(frozen=True)
class ProofCandidate:
    source: str
    proof_id: int
    amount: Decimal
    reference: Optional[str]
    timestamp: Optional[datetime]
    raw_text: str


def _money(value) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _mode_tokens(value: Optional[str]) -> set[str]:
    raw = (value or "").upper().replace("/", ",").replace("+", ",")
    return {part.strip() for part in raw.split(",") if part.strip()}


def _contains_special_mode(value: Optional[str]) -> bool:
    mode = (value or "").upper()
    return any(token in mode for token in SPECIAL_REVIEW_TOKENS)


def _contains_electronic_mode(value: Optional[str]) -> bool:
    tokens = _mode_tokens(value)
    return any(token in ELECTRONIC_MODES for token in tokens)


def _timestamps_align(payment_time: Optional[datetime], proof_time: Optional[datetime]) -> bool:
    if not payment_time or not proof_time:
        return False
    return abs((payment_time - proof_time).total_seconds()) <= 24 * 60 * 60


def _candidate_sort_key(candidate: ProofCandidate):
    source_rank = 0 if candidate.source == "SMS" else 1
    return (source_rank, candidate.timestamp or datetime.min, candidate.proof_id)


def _proof_candidates_for_payments(db: Session, payments: list[Payment]) -> list[ProofCandidate]:
    utrs = {
        payment.utr_reference
        for payment in payments
        if _contains_electronic_mode(payment.mode) and payment.utr_reference
    }
    amounts = {
        payment.amount
        for payment in payments
        if _contains_electronic_mode(payment.mode) and payment.amount is not None
    }
    filters_bank = []
    filters_sms = []
    if utrs:
        filters_bank.append(BankAlert.utr_reference.in_(utrs))
        filters_sms.append(SMSAlert.utr_reference.in_(utrs))
    if amounts:
        filters_bank.append(BankAlert.amount.in_(amounts))
        filters_sms.append(SMSAlert.amount.in_(amounts))

    candidates: list[ProofCandidate] = []
    if filters_sms:
        for proof in db.query(SMSAlert).filter(or_(*filters_sms)).all():
            candidates.append(ProofCandidate(
                source="SMS",
                proof_id=proof.id,
                amount=_money(proof.amount),
                reference=proof.utr_reference,
                timestamp=proof.transaction_timestamp,
                raw_text=proof.raw_body or "",
            ))
    if filters_bank:
        for proof in db.query(BankAlert).filter(or_(*filters_bank)).all():
            candidates.append(ProofCandidate(
                source="BANK_ALERT",
                proof_id=proof.id,
                amount=_money(proof.amount),
                reference=proof.utr_reference,
                timestamp=proof.received_at,
                raw_text=proof.raw_text or "",
            ))
    return sorted(candidates, key=_candidate_sort_key)


def _has_duplicate_payment_utr(db: Session, bill: Bill, payments: list[Payment]) -> bool:
    utrs = [payment.utr_reference for payment in payments if payment.utr_reference]
    if len(utrs) != len(set(utrs)):
        return True
    for utr in utrs:
        count = (
            db.query(Payment)
            .filter(Payment.utr_reference == utr, Payment.bill_id != bill.id)
            .count()
        )
        if count > 0:
            return True
    return False


def _has_same_amount_competing_bill(db: Session, bill: Bill, invoice_amount: Decimal) -> bool:
    if not bill.invoice_date:
        return False
    window_start = bill.invoice_date - timedelta(hours=24)
    window_end = bill.invoice_date + timedelta(hours=24)
    return (
        db.query(Bill)
        .filter(
            Bill.id != bill.id,
            Bill.is_test_data == False,  # noqa: E712
            Bill.amount == invoice_amount,
            Bill.invoice_date != None,  # noqa: E711
            Bill.invoice_date >= window_start,
            Bill.invoice_date <= window_end,
        )
        .count()
        > 0
    )


def _signature_hash(payload: dict) -> str:
    stable = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def build_payment_confirmation_signature(db: Session, bill_id: int) -> dict:
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        raise ValueError(f"Bill not found: {bill_id}")

    payments = (
        db.query(Payment)
        .filter(Payment.bill_id == bill.id)
        .order_by(Payment.payment_date.asc().nullslast(), Payment.created_at.asc())
        .all()
    )
    invoice_amount = _money(bill.amount)
    payment_total = sum((_money(payment.amount) for payment in payments), Decimal("0.00"))
    fallback_total = _money(bill.cash_received) + _money(bill.bank_received) + _money(bill.card_received)
    matched_amount = payment_total if payment_total > 0 else fallback_total
    difference_amount = invoice_amount - matched_amount
    payment_mode = bill.payment_mode or ", ".join(payment.mode for payment in payments if payment.mode) or "UNKNOWN"

    base = {
        "bill_id": bill.id,
        "invoice_no": bill.bill_number,
        "signature_version": SIGNATURE_VERSION,
        "invoice_amount": invoice_amount,
        "matched_amount": matched_amount,
        "difference_amount": difference_amount,
        "payment_mode": payment_mode,
        "payment_status": "PAYMENT_PENDING",
        "confidence_level": "NONE",
        "confidence_score": 0,
        "confidence_reason": "No payment evidence recorded.",
        "proof_status": "NO_PROOF",
        "proof_source": None,
        "proof_id": None,
        "proof_reference": None,
        "proof_timestamp": None,
        "proof_amount": None,
        "requires_accountant_review": True,
        "requires_owner_review": False,
        "verification_state": "SYSTEM_PENDING",
    }

    if _contains_special_mode(payment_mode):
        base.update({
            "payment_status": "REVIEW_REQUIRED",
            "confidence_level": "MEDIUM",
            "confidence_score": 50,
            "confidence_reason": "Advance, old gold exchange, customer purchase, or buyback requires accountant review; digital proof is not attached automatically.",
            "proof_status": "NOT_APPLICABLE",
            "requires_accountant_review": True,
            "verification_state": "ACCOUNTANT_REVIEW",
        })
    elif payment_mode.upper() == "CASH" or (payments and all((payment.mode or "").upper() == "CASH" for payment in payments)):
        base.update({
            "payment_status": "CASH_CONFIRMED",
            "confidence_level": "EXACT",
            "confidence_score": 100,
            "confidence_reason": "Cash payment is auto-confirmed by policy; no digital proof is applicable.",
            "proof_status": "NOT_APPLICABLE",
            "requires_accountant_review": False,
            "verification_state": "SYSTEM_VERIFIED",
        })
    elif _has_duplicate_payment_utr(db, bill, payments):
        base.update({
            "payment_status": "REVIEW_REQUIRED",
            "confidence_level": "LOW",
            "confidence_score": 10,
            "confidence_reason": "Duplicate payment UTR detected across payment rows.",
            "proof_status": "DUPLICATE_PROOF",
            "requires_accountant_review": True,
            "verification_state": "ACCOUNTANT_REVIEW",
        })
    else:
        candidates = _proof_candidates_for_payments(db, payments)
        exact_match = None
        partial_match = None
        mismatch_match = None
        for payment in payments:
            if not _contains_electronic_mode(payment.mode):
                continue
            payment_amount = _money(payment.amount)
            for proof in candidates:
                amount_matches = payment_amount == proof.amount
                reference_matches = bool(payment.utr_reference and proof.reference and payment.utr_reference == proof.reference)
                time_matches = _timestamps_align(payment.payment_date, proof.timestamp)
                if amount_matches and reference_matches and time_matches:
                    exact_match = (payment, proof)
                    break
                if amount_matches and not payment.utr_reference and proof.reference:
                    partial_match = partial_match or (payment, proof)
                elif amount_matches and payment.utr_reference and proof.reference and payment.utr_reference != proof.reference:
                    mismatch_match = mismatch_match or (payment, proof)
            if exact_match:
                break

        if exact_match:
            payment, proof = exact_match
            base.update({
                "payment_status": "VERIFIED",
                "confidence_level": "EXACT",
                "confidence_score": 100,
                "confidence_reason": "Payment amount, mode, UTR/reference, and timestamp align with payment proof.",
                "proof_status": "EXACT_PROOF",
                "proof_source": proof.source,
                "proof_id": proof.proof_id,
                "proof_reference": proof.reference,
                "proof_timestamp": proof.timestamp,
                "proof_amount": proof.amount,
                "requires_accountant_review": False,
                "verification_state": "SYSTEM_VERIFIED",
            })
        elif partial_match:
            payment, proof = partial_match
            base.update({
                "payment_status": "REVIEW_REQUIRED",
                "confidence_level": "MEDIUM",
                "confidence_score": 50,
                "confidence_reason": "payment row missing UTR while proof has UTR; amount matches but proof cannot be verified against the payment row.",
                "proof_status": "PARTIAL_PROOF",
                "proof_source": proof.source,
                "proof_id": proof.proof_id,
                "proof_reference": proof.reference,
                "proof_timestamp": proof.timestamp,
                "proof_amount": proof.amount,
                "requires_accountant_review": True,
                "verification_state": "ACCOUNTANT_REVIEW",
            })
        elif mismatch_match:
            payment, proof = mismatch_match
            base.update({
                "payment_status": "REVIEW_REQUIRED",
                "confidence_level": "LOW",
                "confidence_score": 25,
                "confidence_reason": "Payment UTR does not match proof UTR; amount matches but the reference conflicts.",
                "proof_status": "MISMATCH_PROOF",
                "proof_source": proof.source,
                "proof_id": proof.proof_id,
                "proof_reference": proof.reference,
                "proof_timestamp": proof.timestamp,
                "proof_amount": proof.amount,
                "requires_accountant_review": True,
                "verification_state": "ACCOUNTANT_REVIEW",
            })
        elif matched_amount > 0:
            base.update({
                "payment_status": "REVIEW_REQUIRED",
                "confidence_level": "LOW",
                "confidence_score": 20,
                "confidence_reason": "Payment amount exists but no exact proof was found.",
                "proof_status": "NO_PROOF",
                "requires_accountant_review": True,
                "verification_state": "ACCOUNTANT_REVIEW",
            })

        if base["payment_status"] == "VERIFIED" and _has_same_amount_competing_bill(db, bill, invoice_amount):
            base.update({
                "payment_status": "REVIEW_REQUIRED",
                "confidence_level": "MEDIUM",
                "confidence_score": 50,
                "confidence_reason": "Same amount appears on another customer invoice within 24 hours; accountant review required.",
                "proof_status": "PARTIAL_PROOF",
                "requires_accountant_review": True,
                "verification_state": "ACCOUNTANT_REVIEW",
            })

    hash_payload = {
        key: (str(value) if isinstance(value, Decimal) else value)
        for key, value in base.items()
        if key not in {"signature_hash"}
    }
    base["signature_hash"] = _signature_hash(hash_payload)
    return base
