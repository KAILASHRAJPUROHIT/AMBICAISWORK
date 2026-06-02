import logging
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

from sqlalchemy import or_, and_

def verify_payment_event(db: Session, alert: BankAlert, source: str = "UNKNOWN"):
    """
    Centralized foolproof verification logic for bank events (Email/SMS).
    """
    if alert.reconciled:
        logger.info(f"Alert {alert.id} already reconciled. Skipping.")
        return

    amount = float(alert.amount)
    utr = alert.utr_reference
    received_at = alert.received_at
    
    # 1. Check for ambiguous matches (Multiple invoices with same amount)
    # Using epsilon for numeric comparison in SQLite
    # Search by total_amount OR remaining_amount (to handle split cash+bank)
    matching_bills = db.query(Bill).filter(
        or_(
            and_(Bill.total_amount >= amount - 0.01, Bill.total_amount <= amount + 0.01),
            and_(Bill.remaining_amount >= amount - 0.01, Bill.remaining_amount <= amount + 0.01)
        ),
        Bill.status != "Green"
    ).all()
    
    if not matching_bills:
        # Check if it could be a partial payment for a larger bill matching UTR
        if utr:
            bill_by_utr = db.query(Bill).filter(Bill.reference_no == utr).first()
            if bill_by_utr:
                 matching_bills = [bill_by_utr]
        
    if not matching_bills:
        # If no match found yet, we DO NOT mark reconciled=True.
        # This allows background retry once the invoice is ingested.
        return

    # 2. Multi-Point Scoring for each candidate
    best_bill = None
    best_score = -1
    candidates_count = len(matching_bills)
    
    scored_candidates = []

    for bill in matching_bills:
        score = 0
        
        # A. UTR Match (+100)
        if utr and bill.reference_no and utr == bill.reference_no:
            score += 100
            
        # B. Customer Name Match (+50)
        if bill.customer_name and bill.customer_name.lower() != "unknown":
            name_tokens = [t for t in bill.customer_name.lower().replace("(", " ").replace(")", " ").split() if len(t) > 2]
            raw_text = alert.raw_text.lower()
            matches = sum(1 for t in name_tokens if t in raw_text)
            if len(name_tokens) > 0 and (matches / len(name_tokens)) >= 0.5:
                score += 50
                
        # C. Date Proximity (+30)
        if bill.invoice_date:
            days_diff = (received_at.date() - bill.invoice_date.date()).days
            if 0 <= days_diff <= 3:
                score += 30
            elif -2 <= days_diff <= 7:
                score += 10
        
        # D. Bank Name Match (+20)
        if bill.bank_name and alert.bank_name and bill.bank_name.lower() == alert.bank_name.lower():
            score += 20
            
        scored_candidates.append((bill, score))
        if score > best_score:
            best_score = score
            best_bill = bill

    # 3. Decision Logic
    if best_bill:
        # FOOLPROOF RULES:
        # 1. If multiple candidates have high scores, it's ambiguous.
        high_score_count = sum(1 for b, s in scored_candidates if s >= 80)
        is_ambiguous = (high_score_count > 1 and best_score < 100)
        
        # Check for duplicate UTR usage across the database
        is_duplicate_utr = False
        if utr:
            existing_cleared_payment = db.query(Payment).filter(Payment.utr_reference == utr, Payment.status == "Green").first()
            if existing_cleared_payment and existing_cleared_payment.bill_id != best_bill.id:
                is_duplicate_utr = True
        
        if best_score >= 80 and not is_ambiguous and not is_duplicate_utr:
            # Check if this payment fully covers the remaining amount
            current_bank = float(best_bill.bank_received or 0.0)
            new_bank = current_bank + amount
            
            total_received = float(best_bill.cash_received or 0.0) + new_bank + float(best_bill.card_received or 0.0)
            
            is_fully_paid = abs(total_received - float(best_bill.total_amount)) < 1.0
            
            old_status = best_bill.status
            if is_fully_paid:
                best_bill.status = "Green"
                best_bill.status_text = f"Cleared (Auto-Verified via {source})"
                best_bill.review_required = 0
            else:
                best_bill.status = "Blue"
                best_bill.status_text = f"PARTIALLY_PAID (via {source}): Pending ₹{float(best_bill.total_amount) - total_received:.2f}"
                best_bill.review_required = 1

            # Update specific tracking fields
            if "EMAIL" in source:
                best_bill.email_confirmed_amount = float(best_bill.email_confirmed_amount or 0.0) + amount
            elif "SMS" in source:
                best_bill.sms_confirmed_amount = float(best_bill.sms_confirmed_amount or 0.0) + amount
            
            best_bill.bank_received = new_bank
            best_bill.remaining_amount = float(best_bill.total_amount) - total_received
            best_bill.reference_no = utr or best_bill.reference_no
            
            # Update Payments
            # Find the first pending bank payment and mark it
            payment = db.query(Payment).filter(Payment.bill_id == best_bill.id, Payment.mode == "BANK_TRANSFER", Payment.status != "Green").first()
            if payment:
                if abs(float(payment.amount) - amount) < 1.0:
                    payment.status = "Green"
                    payment.utr_reference = utr or payment.utr_reference

            log_audit(db, "Bill", best_bill.id, "AUTO_VERIFICATION" if is_fully_paid else "PARTIAL_PAYMENT", old_status, best_bill.status, f"Match score: {best_score}")
        else:
            # BLUE / REVIEW REQUIRED
            old_status = best_bill.status
            best_bill.status = "Blue"
            reason = "Ambiguous Match" if is_ambiguous else "Low Confidence Match"
            if not utr: reason = "Missing UTR"
            if is_duplicate_utr: reason = "Duplicate Reference Detected"
            
            best_bill.status_text = f"Review Required: {reason} (Score: {best_score})"
            best_bill.review_required = 1
            log_audit(db, "Bill", best_bill.id, "FLAGGED_FOR_REVIEW", old_status, "Blue", f"{reason}, score: {best_score}")
            
        alert.reconciled = True
        db.commit()

def reconcile_unreconciled_alerts(db: Session):
    """
    Retry reconciliation for all alerts that haven't been matched yet.
    """
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
        metadata_json=json.dumps({"note": note, "timestamp": datetime.now().isoformat()})
    )
    db.add(audit)

def is_store_open(dt: datetime) -> bool:
    """
    Check if store was open at given datetime.
    Mon, Tue, Wed, Fri, Sat, Sun: 10:00 AM - 8:30 PM
    Thu: 12:00 PM - 8:30 PM
    """
    day = dt.weekday() # 0=Mon, 3=Thu
    time = dt.time()
    
    open_time = datetime.strptime("10:00", "%H:%M").time()
    if day == 3: # Thursday
        open_time = datetime.strptime("12:00", "%H:%M").time()
        
    close_time = datetime.strptime("20:30", "%H:%M").time()
    
    return open_time <= time <= close_time
