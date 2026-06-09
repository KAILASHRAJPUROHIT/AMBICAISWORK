from typing import List, Dict, Any
from sqlalchemy.orm import Session
from datetime import timedelta
from backend.models import Bill, Payment, PaymentConfirmationSignature, BankAlert, SMSAlert, AccountantVerificationQueue

def compute_payment_signature(db: Session, bill: Bill, payments: List[Payment]) -> Dict[str, Any]:
    """
    Single Payment Signature & Dashboard Truth Model.
    Derives dashboard state dynamically from available evidence without mutating the database.
    """
    stored_bill_status = bill.status or "Pending"
    
    # Defaults
    dashboard_state = "Review Required"
    dashboard_confidence = "Low"
    integrity_status = "CONSISTENT"
    verification_source = "UNKNOWN"
    review_required = False
    warning_reason = ""
    vetoes = []
    
    payment_breakdown = []
    
    # Priority for aggregation
    priority_map = {
        "Queued for accountant review": 1,
        "Proof mismatch": 2,
        "no_proof": 2,
        "Proof verified": 3,
        "Payment proof not needed": 4
    }
    def get_priority(label):
        return priority_map.get(label, 99)

    overall_proof_status = "no_proof"
    has_advance_or_old_gold = False
    is_cash_only = True

    for p in payments:
        mode_up = (p.mode or "UNKNOWN").upper()
        if mode_up != "CASH":
            is_cash_only = False
            
        if mode_up in ["ADVANCE", "OLD_GOLD_EXCHANGE", "CUST PURCHASE"]:
            has_advance_or_old_gold = True
            
        p_proof_label = "no_proof"
        p_proof_url = ""
        p_sources = []
        
        if mode_up == "CASH":
            p_proof_label = "Payment proof not needed"
        elif mode_up in ["ADVANCE", "OLD_GOLD_EXCHANGE", "CUST PURCHASE"]:
            p_proof_label = "Queued for accountant review"
        elif mode_up in ["UPI", "IMPS", "NEFT", "RTGS", "CARD", "CHEQUE"]:
            p_time = p.created_at
            if p_time and mode_up in ["UPI", "IMPS", "NEFT", "RTGS"]:
                time_min = p_time - timedelta(minutes=5)
                time_max = p_time + timedelta(minutes=5)
                
                bank_alerts = db.query(BankAlert).filter(
                    BankAlert.amount == p.amount,
                    BankAlert.received_at >= time_min,
                    BankAlert.received_at <= time_max
                ).all()
                
                sms_alerts = db.query(SMSAlert).filter(
                    SMSAlert.amount == p.amount,
                    SMSAlert.transaction_timestamp >= time_min,
                    SMSAlert.transaction_timestamp <= time_max
                ).all()
                
                if p.utr_reference and bank_alerts and sms_alerts:
                    ba_match = any(ba.utr_reference == p.utr_reference for ba in bank_alerts)
                    sa_match = any(sa.utr_reference == p.utr_reference for sa in sms_alerts)
                    if ba_match and sa_match:
                        p_proof_label = "Proof verified"
                        for ba in bank_alerts:
                            if ba.utr_reference == p.utr_reference:
                                if not p_proof_url: p_proof_url = f"/api/reconciliation/proof/bank/{ba.id}"
                                p_sources.append({"type": "Bank Alert", "details": ba.raw_text, "status": "unified"})
                        for sa in sms_alerts:
                            if sa.utr_reference == p.utr_reference:
                                if not p_proof_url: p_proof_url = f"/api/reconciliation/proof/sms/{sa.id}"
                                p_sources.append({"type": "SMS Alert", "details": sa.raw_body, "status": "unified"})
                    else:
                        p_proof_label = "Proof mismatch"
                elif bank_alerts or sms_alerts:
                    p_proof_label = "Proof mismatch"
                else:
                    p_proof_label = "no_proof"
        
        if get_priority(p_proof_label) < get_priority(overall_proof_status) or overall_proof_status == "no_proof":
            overall_proof_status = p_proof_label
            
        payment_breakdown.append({
            "payment_id": p.id,
            "amount": float(p.amount) if p.amount else 0.0,
            "mode": p.mode or "UNKNOWN",
            "proof_label": p_proof_label,
            "proof_url": p_proof_url,
            "proof_exists": bool(p_proof_url),
            "proof_source": "",
            "utr_reference": p.utr_reference or "",
            "timestamp": p.created_at.strftime("%H:%M %p") if p.created_at else "",
            "sources": p_sources
        })

    # Load Queue Status
    # Sort queues by descending created_at to get the latest
    latest_queue = db.query(AccountantVerificationQueue).filter(
        AccountantVerificationQueue.bill_id == bill.id
    ).order_by(AccountantVerificationQueue.created_at.desc()).first()
    
    is_queue_open = latest_queue and latest_queue.queue_status in ["OPEN", "FURTHER_REVIEW", "OWNER_ESCALATION_PENDING"]
    is_accountant_approved = latest_queue and latest_queue.queue_status == "APPROVED"

    # Evaluation Rules
    if is_cash_only:
        overall_proof_status = "Payment proof not needed"
        if stored_bill_status in ("Green", "Verified"):
            dashboard_state = "Green"
            dashboard_confidence = "Medium"
            verification_source = "CASH_NO_PROOF_REQUIRED"
        else:
            dashboard_state = "Review Required"
            dashboard_confidence = "Low"
            verification_source = "UNKNOWN"

    elif has_advance_or_old_gold:
        overall_proof_status = "Queued for accountant review"
        if is_accountant_approved and stored_bill_status in ("Green", "Verified"):
            dashboard_state = "Green"
            dashboard_confidence = "High"
            integrity_status = "CONSISTENT"
            verification_source = "ACCOUNTANT_APPROVED"
        else:
            dashboard_state = "Accountant Review Required"
            dashboard_confidence = "Low"
            integrity_status = "REVIEW_REQUIRED"
            review_required = True
            if stored_bill_status in ("Green", "Verified"):
                integrity_status = "CONTRADICTORY_STATE"
                warning_reason = "Advance or Old Gold Exchange payment requires accountant review but is stored as Green"

    else:
        # Standard Banking Modes
        if overall_proof_status == "no_proof":
            dashboard_confidence = "Low"
            if stored_bill_status in ("Green", "Verified"):
                integrity_status = "CONTRADICTORY_STATE"
                dashboard_state = "Review Required"
                warning_reason = "Green bill has missing required UPI proof"
            else:
                integrity_status = "MISSING_PROOF"
                dashboard_state = "Review Required"
                
        elif overall_proof_status == "Proof mismatch":
            dashboard_confidence = "Low"
            if stored_bill_status in ("Green", "Verified"):
                integrity_status = "CONTRADICTORY_STATE"
                dashboard_state = "Review Required"
                warning_reason = "Green bill has mismatched required proof"
            else:
                integrity_status = "FAILED_OR_REVERSED_PROOF"
                dashboard_state = "Review Required"

        elif overall_proof_status == "Queued for accountant review":
            dashboard_confidence = "Low"
            if stored_bill_status in ("Green", "Verified"):
                integrity_status = "CONTRADICTORY_STATE"
                dashboard_state = "Review Required"
                warning_reason = "Green bill has proof queued for review"
            else:
                integrity_status = "REVIEW_REQUIRED"
                dashboard_state = "Accountant Review Required"

        elif overall_proof_status == "Proof verified":
            if stored_bill_status in ("Green", "Verified"):
                dashboard_state = "Green"
                dashboard_confidence = "High"
                integrity_status = "CONSISTENT"
                verification_source = "AUTO_DETERMINISTIC"
            else:
                dashboard_state = "Review Required"
                dashboard_confidence = "Low"
                integrity_status = "CONSISTENT"

    if is_queue_open:
        review_required = True
        dashboard_confidence = "Low"
        dashboard_state = "Accountant Review Required"
        if stored_bill_status in ("Green", "Verified"):
            integrity_status = "CONTRADICTORY_STATE"
            warning_reason = "Open accountant queue exists for Green bill"
        else:
            integrity_status = "REVIEW_REQUIRED"

    proof_exists = False
    proof_url = None
    for p in payment_breakdown:
        if p["proof_exists"] and p["mode"] in ["UPI", "IMPS", "NEFT", "RTGS", "CARD", "CHEQUE"]:
            proof_exists = True
            if not proof_url:
                proof_url = p["proof_url"]

    # Enforce strict vetoes per Single Truth Engine Law
    if dashboard_state == "Green" and overall_proof_status == "no_proof" and not is_cash_only:
        review_required = True
        dashboard_confidence = "Low"
        vetoes.append("GREEN_WITHOUT_PROOF")

    if review_required and dashboard_confidence == "High":
        integrity_status = "CONTRADICTORY_STATE"
        vetoes.append("HIGH_CONFIDENCE_REVIEW_REQUIRED")

    return {
        "stored_bill_status": stored_bill_status,
        "proof_status": overall_proof_status,
        "proof_exists": proof_exists,
        "proof_url": proof_url,
        "payment_breakdown": payment_breakdown,
        "review_required": review_required,
        "integrity_status": integrity_status,
        "verification_source": verification_source,
        "confidence": dashboard_confidence,
        "state": dashboard_state,
        "warning_reason": warning_reason,
        "vetoes": vetoes
    }
