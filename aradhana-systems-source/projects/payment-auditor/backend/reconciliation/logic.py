import logging
from typing import List, Union, Dict, Optional
from sqlalchemy.orm import Session
from backend.models import Bill, Payment, BankAlert, AuditLog, Cheque, SMSAlert
from datetime import datetime, timedelta
import json
import hashlib

logger = logging.getLogger("Reconciliation_Logic")

def get_event_fingerprint(bank, amount, utr, received_at, direction="CREDIT"):
    date_str = received_at.strftime("%Y-%m-%d")
    raw = f"{bank}|{amount:.2f}|{utr}|{date_str}|{direction}"
    return hashlib.sha256(raw.encode()).hexdigest()

from sqlalchemy import or_, and_, func

def verify_payment_event(db: Session, alert: BankAlert, source: str = "UNKNOWN"):
    """
    Financial Hardening Edition: Centralized foolproof verification logic.
    Primary Principle: Never auto-confirm uncertain payments.
    """
    if alert.reconciled:
        logger.info(f"Alert {alert.id} already reconciled. Skipping.")
        return

    amount = float(alert.amount)
    utr = alert.utr_reference
    received_at = alert.received_at
    
    # 1. Check for ambiguous matches (Multiple invoices with same amount)
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

    # 2. Multi-Point Scoring for each candidate
    best_bill = None
    best_score = -1
    scored_candidates = []

    for bill in matching_bills:
        score = 0
        
        # A. UTR Match (+100)
        if utr and bill.reference_no and utr == bill.reference_no:
            score += 100

        # B. Exact Remaining Amount Match (+100)
        # Mandate: If alert matches exactly what's left after CASH/ADV/GOLD
        if abs(float(bill.remaining_amount or 0) - amount) < 0.01:
            score += 100
            
        # C. Customer Name Match (+50)
        if bill.customer_name and bill.customer_name.lower() != "unknown":
            name_tokens = [t for t in bill.customer_name.lower().replace("(", " ").replace(")", " ").split() if len(t) > 2]
            raw_text = alert.raw_text.lower()
            matches = sum(1 for t in name_tokens if t in raw_text)
            if len(name_tokens) > 0 and (matches / len(name_tokens)) >= 0.5:
                score += 50
                
        # D. Date Proximity (+30)
        if bill.invoice_date:
            days_diff = (received_at.date() - bill.invoice_date.date()).days
            if 0 <= days_diff <= 3:
                score += 30
            elif -2 <= days_diff <= 7:
                score += 10
        
        # E. Bank Name Match (+20)
        if bill.bank_name and alert.bank_name and bill.bank_name.lower() == alert.bank_name.lower():
            score += 20
            
        scored_candidates.append((bill, score))
        if score > best_score:
            best_score = score
            best_bill = bill

    # 3. Decision Logic with Failsafes
    if best_bill:
        # Rule 4: Ambiguity Control
        # If multiple candidates have high scores, it's ambiguous.
        is_ambiguous = (len(matching_bills) > 1 and best_score < 100)
        
        # Rule 3: Duplicate UTR Detection
        is_duplicate_utr = False
        if utr:
            existing_cleared_payment = db.query(Payment).filter(
                Payment.utr_reference == utr, 
                Payment.status == "Green"
            ).first()
            if existing_cleared_payment and existing_cleared_payment.bill_id != best_bill.id:
                is_duplicate_utr = True

        # Rule: Historical Payment Claim Detection
        is_historical_claim = False
        historical_payment = db.query(Payment).filter(
            Payment.bill_id == best_bill.id,
            Payment.payment_date != None,
            func.date(Payment.payment_date) < func.date(best_bill.invoice_date)
        ).first()
        if historical_payment:
            is_historical_claim = True
        
        logger.info(f"Recon Decision for {best_bill.bill_number}: Score={best_score}, Ambiguous={is_ambiguous}, DuplicateUTR={is_duplicate_utr}, HistClaim={is_historical_claim}")
        
        # Rule 1: Advance Verification Failsafe
        has_advance = float(best_bill.advance_amount or 0.0) > 0
        advance_unclassified = has_advance and (not best_bill.advance_source or best_bill.advance_source == "UNKNOWN")
        
        # Decision
        if best_score >= 80 and not is_ambiguous and not is_duplicate_utr and not is_historical_claim:
            # Check if this payment fully covers the remaining amount
            current_bank = float(best_bill.bank_received or 0.0)
            new_bank = current_bank + amount
            
            # total_received = confirmed_cash + new_bank + card
            # Mandate 2: Treat cash amount as ERP-confirmed cash receipt.
            total_received = float(best_bill.cash_received or 0.0) + new_bank + float(best_bill.card_received or 0.0)
            
            # Plus credits (advance and purchase)
            total_credits = total_received + float(best_bill.advance_amount or 0.0) + float(best_bill.customer_purchase_amount or 0.0)
            
            is_fully_paid = abs(total_credits - float(best_bill.total_amount)) < 1.0
            
            old_status = best_bill.status
            
            # FINAL CLEARANCE CHECK
            if is_fully_paid:
                if advance_unclassified:
                    best_bill.status = "Purple"
                    best_bill.status_text = "ADVANCE_PAYMENT_TYPE_UNKNOWN"
                    best_bill.review_required = 1
                elif has_advance and best_bill.advance_verification_status != "VERIFIED":
                    best_bill.status = "Blue"
                    best_bill.status_text = "ADVANCE_REQUIRES_VERIFICATION"
                    best_bill.review_required = 1
                else:
                    best_bill.status = "Green"
                    # Rule 4: CASH_PLUS_BANK_CONFIRMED
                    if float(best_bill.cash_received or 0) > 0:
                        best_bill.status_text = "Cleared (CASH_PLUS_BANK_CONFIRMED)"
                    else:
                        best_bill.status_text = f"Cleared (Auto-Verified via {source})"
                    best_bill.review_required = 0
            else:
                if advance_unclassified:
                    best_bill.status = "Purple"
                    best_bill.status_text = "ADVANCE_PAYMENT_TYPE_UNKNOWN"
                else:
                    best_bill.status = "Blue"
                    best_bill.status_text = f"PARTIALLY_PAID (via {source}): Pending ₹{float(best_bill.total_amount) - total_credits:.2f}"
                best_bill.review_required = 1

            # Rule 6: Delivery Before Payment Control
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
            # FAILSAFE PATH: RED or BLUE or PURPLE
            old_status = best_bill.status
            reason = "AMBIGUOUS_AMOUNT_MATCH" if is_ambiguous else "LOW_CONFIDENCE_MATCH"
            if not utr: reason = "MISSING_UTR"
            
            if is_duplicate_utr:
                best_bill.status = "Red"
                reason = "DUPLICATE_UTR"
            elif is_historical_claim:
                best_bill.status = "Purple"
                reason = "HISTORICAL_PAYMENT_VERIFICATION"
                if float(historical_payment.amount) >= 50000.0:
                    reason += " [HIGH_VALUE_ESCALATION]"
            else:
                best_bill.status = "Blue"
            
            best_bill.status_text = f"Review Required: {reason} (Score: {best_score})"
            best_bill.review_required = 1
            log_audit(db, "Bill", best_bill.id, "FLAGGED_FOR_REVIEW", old_status, best_bill.status, f"{reason}, score: {best_score}")
            
        alert.reconciled = True
        db.commit()

def reconcile_unreconciled_alerts(db: Session):
    unreconciled = db.query(BankAlert).filter(BankAlert.reconciled == False).all()
    if not unreconciled:
        return
        
    logger.info(f"Retrying reconciliation for {len(unreconciled)} unreconciled alerts...")
    for alert in unreconciled:
        verify_payment_event(db, alert, source="RETRY_LOGIC")

def log_audit(db, entity_type, entity_id, action, old_status, new_status, note=""):
    audit = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_status=old_status,
        new_status=new_status,
        actor="SYSTEM",
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

    # Determine the effective UTR/reference for the payment based on mode
    payment_utr = None
    if payment.mode in ["UPI", "IMPS", "NEFT", "RTGS_OR_CHEQUE", "CARD", "BANK_TRANSFER"]:
        # For electronic modes, use payment's own UTR only. No fallback to bill.reference_no here.
        payment_utr = payment.utr_reference
    # For CASH, ADVANCE, OLD_GOLD_EXCHANGE, payment_utr remains None.

    if payment.mode == "CASH":
        result.update({
            "proof_status": "confirmed_received",
            "proof_type": "Cash",
            "proof_label": "Cash auto-confirmed",
            "confidence_score": 100,
            "confidence_reason": "Auto-confirmed as per policy (CASH payments)",
            "requires_accountant_review": False
        })
    elif payment.mode in ["ADVANCE", "OLD_GOLD_EXCHANGE"]: # OLD_GOLD_EXCHANGE is 'CUST PURCHASE' in prompt
        result.update({
            "proof_status": "pending_accountant_review",
            "proof_type": payment.mode,
            "proof_label": f"Accountant review required for {payment.mode}",
            "confidence_score": 0,
            "confidence_reason": f"Requires manual accountant confirmation for {payment.mode}",
            "requires_accountant_review": True
        })
    elif payment.mode in ["UPI", "IMPS", "NEFT", "RTGS_OR_CHEQUE", "CARD", "BANK_TRANSFER"]: # These are 'UPI/BANK/CARD/ONLINE'
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
            
            # Check for exact match: UTR and Amount
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
                break # Found exact match, no need to check other proofs
            
            # Check for partial match: Amount only (if UTR is missing or mismatched)
            if (not found_match and abs(float(payment.amount) - float(proof_amount)) < 0.01 and
                (not payment_utr or not proof_utr or payment_utr != proof_utr)):
                 # This is a potential match, but with UTR discrepancy
                 result.update({
                    "proof_status": "mismatch_proof",
                    "proof_type": proof_type_str,
                    "proof_id": proof_id,
                    "proof_label": f"Partial Proof from {proof_type_str} (ID: {proof_id}): Amount matches, UTR differs/missing",
                    "confidence_score": 50,
                    "confidence_reason": f"Amount matches {proof_type_str} proof, but UTR is missing or mismatched.",
                    "requires_accountant_review": True
                })
                 # Don't break, keep looking for exact matches
                 
        if found_match:
            pass # Already updated in the loop
        elif result["proof_status"] != "mismatch_proof": # If no exact match and no partial match
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
