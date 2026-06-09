import logging
from typing import List, Union, Dict, Optional
from sqlalchemy.orm import Session
from backend.models import Bill, Payment, BankAlert, AuditLog, Cheque, SMSAlert, AccountantVerificationQueue
from datetime import datetime, timedelta
import json
import hashlib
from sqlalchemy import or_, and_, func

logger = logging.getLogger("Reconciliation_Logic")

def get_event_fingerprint(bank, amount, utr, received_at, direction="CREDIT"):
    date_str = received_at.strftime("%Y-%m-%d")
    raw = f"{bank}|{amount:.2f}|{utr}|{date_str}|{direction}"
    return hashlib.sha256(raw.encode()).hexdigest()

def verify_payment_event(db: Session, alert: BankAlert, source: str = "UNKNOWN"):
    """
    Super Strict Hardening Edition: Deterministic rules with 150-point threshold and hard vetoes.
    """
    if alert.reconciled:
        logger.info(f"Alert {alert.id} already reconciled. Skipping.")
        return

    amount = float(alert.amount)
    utr = alert.utr_reference
    received_at = alert.received_at
    raw_text = alert.raw_text.lower() if alert.raw_text else ""
    
    # 1. Proof Classification Layer
    failure_keywords = ["failed", "failure", "declined", "reversed", "reversal", "returned", "chargeback", "cancelled", "timeout", "unsuccessful", "not processed"]
    is_failed_or_reversed = any(kw in raw_text for kw in failure_keywords)
    
    # Candidate Search
    matching_bills = db.query(Bill).filter(
        Bill.is_test_data == False,
        or_(
            and_(Bill.total_amount >= amount - 0.01, Bill.total_amount <= amount + 0.01),
            and_(Bill.remaining_amount >= amount - 0.01, Bill.remaining_amount <= amount + 0.01)
        ),
        Bill.status != "Green"
    ).all()
    
    if not matching_bills and utr:
        bill_by_utr = db.query(Bill).filter(Bill.reference_no == utr, Bill.is_test_data == False).first()
        if bill_by_utr:
             matching_bills = [bill_by_utr]
        
    if not matching_bills:
        return

    # Pre-calculate Today candidates to enforce Today-First priority
    today_bills = [b for b in matching_bills if b.invoice_date and b.invoice_date.date() == received_at.date()]
    has_today_candidate = len(today_bills) > 0

    best_bill = None
    best_score = -1
    best_vetoes = []
    best_queue_reason = None

    for bill in matching_bills:
        vetoes = []
        queue_reason = None
        
        # Determine mode (using Payments attached to the bill, or default)
        payment_mode_query = db.query(Payment.mode).filter(Payment.bill_id == bill.id).first()
        invoice_mode = payment_mode_query[0] if payment_mode_query else "UNKNOWN"
        
        # --- HARD VETOES ---
        
        # Hard Veto 1: FAILURE_OR_REVERSAL_BLOCK
        if is_failed_or_reversed:
            vetoes.append("FAILURE_OR_REVERSAL_BLOCK")
            queue_reason = queue_reason or "FAILED_OR_REVERSED_PROOF"
            
        # Hard Veto 2: OPEN_QUEUE_VETO
        open_queue = db.query(AccountantVerificationQueue).filter(
            AccountantVerificationQueue.bill_id == bill.id,
            AccountantVerificationQueue.queue_status == 'OPEN'
        ).first()
        if open_queue:
            vetoes.append("OPEN_QUEUE_VETO")
            queue_reason = queue_reason or "OPEN_QUEUE_VETO"
            
        # Hard Veto 3: NAME_MISMATCH_BLOCK
        name_score = 0
        if bill.customer_name and bill.customer_name.lower() != "unknown" and raw_text:
            name_tokens = [t for t in bill.customer_name.lower().replace("(", " ").replace(")", " ").split() if len(t) > 2]
            if len(name_tokens) > 0:
                matches = sum(1 for t in name_tokens if t in raw_text)
                if (matches / len(name_tokens)) >= 0.5:
                    name_score = 25
                else:
                    vetoes.append("NAME_MISMATCH_BLOCK")
                    queue_reason = queue_reason or "CUSTOMER_NAME_MISMATCH"

        # Hard Veto 4: PAYMENT_MODE_MISMATCH_BLOCK
        is_bank_source = source in ["SMS_ALERT", "BANK_ALERT", "BANK", "SMS", "RETRY_LOGIC"] or isinstance(alert, BankAlert) or isinstance(alert, SMSAlert)
        mode_score = 0
        if invoice_mode in ["UPI", "IMPS", "NEFT", "RTGS_OR_CHEQUE", "BANK_TRANSFER", "CARD", "UNKNOWN"] and is_bank_source:
            mode_score = 25
        elif invoice_mode == "CASH" and is_bank_source:
            vetoes.append("PAYMENT_MODE_MISMATCH_BLOCK")
            queue_reason = queue_reason or "PAYMENT_MODE_MISMATCH"

        # Hard Veto 5: TIME_WINDOW_BLOCK & HISTORICAL_MATCH_VETO
        time_score = 0
        is_past_bill = False
        if bill.invoice_date:
            days_diff = (received_at.date() - bill.invoice_date.date()).days
            if 0 <= days_diff <= 3:
                time_score = 25
            elif days_diff < 0 or days_diff > 3:
                if days_diff > 3:
                    is_past_bill = True
                vetoes.append("TIME_WINDOW_BLOCK")
                queue_reason = queue_reason or "PAYMENT_TIME_MISMATCH"
                
        if is_past_bill:
            vetoes.append("HISTORICAL_MATCH_VETO")
            queue_reason = queue_reason or "SUGGESTED_HISTORICAL_MATCH"
            
        # Hard Veto 6: TODAY-FIRST PRIORITY RULE
        if is_past_bill and has_today_candidate:
            vetoes.append("TODAY_FIRST_PRIORITY_BLOCK")
            queue_reason = queue_reason or "TODAY_BILL_PRIORITY_CONFLICT"

        # Check for multiple today candidates
        if has_today_candidate and len(today_bills) > 1 and bill in today_bills:
            vetoes.append("MULTIPLE_TODAY_CANDIDATES_BLOCK")
            queue_reason = queue_reason or "DUPLICATE_SAME_AMOUNT_TODAY"

        # --- PROBABILITY SCORING (Max ~225) ---
        score = 0
        
        # Amount match (+25)
        if abs(float(bill.remaining_amount or 0) - amount) < 0.01 or abs(float(bill.total_amount) - amount) < 0.01:
            score += 25
            
        # UTR Match (+50)
        utr_match = False
        if utr and bill.reference_no and utr == bill.reference_no:
            score += 50
            utr_match = True
            
        # Success proof (+50)
        if not is_failed_or_reversed:
            score += 50
            
        # Mode match (+25)
        score += mode_score
        
        # Time match (+25)
        score += time_score
        
        # Customer match (+25)
        score += name_score
        
        # Invoice reference match (+25)
        if bill.bill_number and bill.bill_number.lower() in raw_text:
            score += 25
            
        if score > best_score:
            best_score = score
            best_bill = bill
            best_vetoes = vetoes
            best_queue_reason = queue_reason

    # --- DECISION LOGIC ---
    if best_bill:
        # Check duplicate UTR rule
        is_duplicate_utr = False
        if utr:
            existing_cleared_payment = db.query(Payment).filter(
                Payment.utr_reference == utr, 
                Payment.status == "Green"
            ).first()
            if existing_cleared_payment and existing_cleared_payment.bill_id != best_bill.id:
                is_duplicate_utr = True
                best_vetoes.append("DUPLICATE_UTR_BLOCK")
                best_queue_reason = best_queue_reason or "DUPLICATE_UTR"
                
        # Advance Failsafe
        has_advance = float(best_bill.advance_amount or 0.0) > 0
        advance_unclassified = has_advance and (not best_bill.advance_source or best_bill.advance_source == "UNKNOWN")
        if advance_unclassified or (has_advance and best_bill.advance_verification_status != "VERIFIED"):
            best_vetoes.append("ADVANCE_FAILSAFE_BLOCK")
            
        logger.info(f"Recon Decision for {best_bill.bill_number}: Score={best_score}, Vetoes={best_vetoes}")
        
        is_fully_paid = False
        total_credits = 0.0
        new_bank = float(best_bill.bank_received or 0.0) + amount
        
        if best_score >= 150 and not best_vetoes:
            # AUTO_VERIFY_ALLOWED
            total_received = float(best_bill.cash_received or 0.0) + new_bank + float(best_bill.card_received or 0.0)
            total_credits = total_received + float(best_bill.advance_amount or 0.0) + float(best_bill.customer_purchase_amount or 0.0)
            is_fully_paid = abs(total_credits - float(best_bill.total_amount)) < 1.0
            old_status = best_bill.status
            
            if is_fully_paid:
                best_bill.status = "Green"
                if float(best_bill.cash_received or 0) > 0:
                    best_bill.status_text = "Cleared (CASH_PLUS_BANK_CONFIRMED)"
                else:
                    best_bill.status_text = f"Cleared (Auto-Verified via {source})"
                best_bill.review_required = 0
            else:
                best_bill.status = "Blue"
                best_bill.status_text = f"PARTIALLY_PAID (via {source}): Pending ₹{float(best_bill.total_amount) - total_credits:.2f}"
                best_bill.review_required = 1

            if best_bill.is_delivered and not is_fully_paid:
                best_bill.status = "Orange"
                best_bill.status_text = "DELIVERED_BEFORE_PAYMENT"
                best_bill.review_required = 1
                
            # Update specific tracking fields
            if "EMAIL" in source:
                best_bill.email_confirmed_amount = float(best_bill.email_confirmed_amount or 0.0) + amount
            elif "SMS" in source:
                best_bill.sms_confirmed_amount = float(best_bill.sms_confirmed_amount or 0.0) + amount
                
            best_bill.bank_received = new_bank
            best_bill.remaining_amount = float(best_bill.total_amount) - total_credits
            if best_bill.remaining_amount < 0: best_bill.remaining_amount = 0
            best_bill.reference_no = utr or best_bill.reference_no
            
            # Update Payments table
            payment = db.query(Payment).filter(Payment.bill_id == best_bill.id, Payment.mode.in_(["BANK_TRANSFER", "UPI", "IMPS", "NEFT", "RTGS_OR_CHEQUE"]), Payment.status != "Green").first()
            if payment:
                if abs(float(payment.amount) - amount) < 1.0:
                    payment.status = "Green"
                    payment.utr_reference = utr or payment.utr_reference

            log_audit(db, "Bill", best_bill.id, "AUTO_VERIFICATION" if best_bill.status == "Green" else "SAFE_MATCH", old_status, best_bill.status, f"Match score: {best_score}")
        else:
            # ACCOUNTANT_REVIEW (Hard Veto or Low Score)
            old_status = best_bill.status
            reason = best_queue_reason or "LOW_CONFIDENCE_MATCH"
            if not utr and not best_queue_reason: reason = "MISSING_UTR"
            
            if "DUPLICATE_UTR_BLOCK" in best_vetoes:
                best_bill.status = "Red"
            elif "SUGGESTED_HISTORICAL_MATCH" in best_vetoes or "TODAY_BILL_PRIORITY_CONFLICT" in best_vetoes:
                best_bill.status = "Purple"
            else:
                best_bill.status = "Blue"
                
            if "OPEN_QUEUE_VETO" in best_vetoes:
                # Do not mutate the status to Blue/Purple/Red if there's already an open queue. Keep existing or rely on queue.
                pass
                
            best_bill.status_text = f"Review Required: {reason} (Score: {best_score})"
            best_bill.review_required = 1
            log_audit(db, "Bill", best_bill.id, "FLAGGED_FOR_REVIEW", old_status, best_bill.status, f"{reason}, score: {best_score}, vetoes: {best_vetoes}")
            
        alert.reconciled = True
        db.commit()

def reconcile_unreconciled_alerts(db: Session):
    unreconciled = db.query(BankAlert).filter(BankAlert.reconciled == False).all()
    if not unreconciled:
        return
        
    logger.info(f"Retrying reconciliation for {len(unreconciled)} unreconciled alerts...")
    for alert in unreconciled:
        verify_payment_event(db, alert, source="RETRY_LOGIC")

def log_audit(db, entity_type, entity_id, action, old_status, new_status, note="", actor="SYSTEM"):
    audit = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_status=old_status,
        new_status=new_status,
        actor=actor,
        metadata_json=json.dumps({
            "note": note, 
            "timestamp": datetime.now().isoformat(),
            "source": "Reconciliation_Engine"
        })
    )
    db.add(audit)

def calculate_payment_proof_status(payment: Payment, bill: Bill, proofs: List[Union[SMSAlert, BankAlert]]) -> Dict:
    """
    Centralized helper to determine payment proof status, confidence, and review requirements.
    """
    result = {
        "proof_status": "no_proof",
        "proof_type": None,
        "proof_id": None,
        "proof_label": "No proof found",
        "confidence_score": 0,
        "confidence_reason": "No matching proof found",
        "requires_accountant_review": True
    }

    payment_utr = None
    if payment.mode in ["UPI", "IMPS", "NEFT", "RTGS_OR_CHEQUE", "CARD", "BANK_TRANSFER"]:
        payment_utr = payment.utr_reference

    if payment.mode == "CASH":
        result.update({
            "proof_status": "confirmed_received",
            "proof_type": "Cash",
            "proof_label": "Cash auto-confirmed",
            "confidence_score": 100,
            "confidence_reason": "Auto-confirmed as per policy (CASH payments)",
            "requires_accountant_review": False
        })
    elif payment.mode in ["ADVANCE", "OLD_GOLD_EXCHANGE"]:
        result.update({
            "proof_status": "pending_accountant_review",
            "proof_type": payment.mode,
            "proof_label": f"Accountant review required for {payment.mode}",
            "confidence_score": 0,
            "confidence_reason": f"Requires manual accountant confirmation for {payment.mode}",
            "requires_accountant_review": True
        })
    elif payment.mode in ["UPI", "IMPS", "NEFT", "RTGS_OR_CHEQUE", "CARD", "BANK_TRANSFER"]:
        found_match = False
        for proof in proofs:
            proof_utr = None
            proof_amount = None
            proof_type_str = None
            proof_id = None

            if isinstance(proof, SMSAlert):
                proof_utr = proof.utr_reference
                proof_amount = proof.amount
                proof_type_str = "SMS"
                proof_id = proof.id
            elif isinstance(proof, BankAlert):
                proof_utr = proof.utr_reference
                proof_amount = proof.amount
                proof_type_str = "Bank"
                proof_id = proof.id
            
            if (payment_utr and proof_utr and payment_utr == proof_utr and
                abs(float(payment.amount) - float(proof_amount)) < 0.01):
                result.update({
                    "proof_status": "verified_proof",
                    "proof_type": proof_type_str,
                    "proof_id": proof_id,
                    "proof_label": f"Verified by {proof_type_str} Proof (ID: {proof_id})",
                    "confidence_score": 100,
                    "confidence_reason": f"Exact UTR and amount match with {proof_type_str} proof.",
                    "requires_accountant_review": False
                })
                found_match = True
                break
            
            if (not found_match and abs(float(payment.amount) - float(proof_amount)) < 0.01 and
                (not payment_utr or not proof_utr or payment_utr != proof_utr)):
                 result.update({
                    "proof_status": "mismatch_proof",
                    "proof_type": proof_type_str,
                    "proof_id": proof_id,
                    "proof_label": f"Partial Proof from {proof_type_str} (ID: {proof_id}): Amount matches, UTR differs/missing",
                    "confidence_score": 50,
                    "confidence_reason": f"Amount matches {proof_type_str} proof, but UTR is missing or mismatched.",
                    "requires_accountant_review": True
                })
                 
        if found_match:
            pass
        elif result["proof_status"] != "mismatch_proof":
            result.update({
                "proof_status": "no_proof",
                "proof_type": None,
                "proof_id": None,
                "proof_label": "No proof found for bank/online payment",
                "confidence_score": 0,
                "confidence_reason": "No matching SMS or Bank proof found for bank/online payment.",
                "requires_accountant_review": True
            })
    
    return result

def is_store_open(dt: datetime) -> bool:
    day = dt.weekday()
    time = dt.time()
    open_time = datetime.strptime("10:00", "%H:%M").time()
    if day == 3: open_time = datetime.strptime("12:00", "%H:%M").time()
    close_time = datetime.strptime("20:30", "%H:%M").time()
    return open_time <= time <= close_time
