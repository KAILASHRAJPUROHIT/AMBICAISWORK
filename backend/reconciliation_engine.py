from typing import List, Any
from backend.schemas import ReconciliationDecision
from datetime import datetime, timedelta

def get_date(obj: Any, field_name: str) -> datetime:
    val = getattr(obj, field_name, None)
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace('Z', '+00:00'))
        except:
            return datetime.now()
    elif isinstance(val, datetime):
        return val
    return datetime.now()

def reconcile_transactions(bills: List[Any], payments: List[Any], bank_alerts: List[Any], sms_alerts: List[Any], cheques: List[Any]) -> ReconciliationDecision:
    if not bills:
        return ReconciliationDecision(
            status="Green",
            reason="No bills to process",
            risk_flags=[],
            requires_human_review=False
        )

    risk_flags = []
    status = "Green"
    requires_human_review = False
    reasons = []

    all_alerts = bank_alerts + sms_alerts

    # 1. Duplicate UTR Detection across all bills
    utrs_in_bills = [getattr(b, 'utr_reference', None) for b in bills if getattr(b, 'utr_reference', None)]
    if len(utrs_in_bills) != len(set(utrs_in_bills)):
        risk_flags.append("Duplicate UTR in Bills")
        status = "Red"
        requires_human_review = True
        reasons.append("Duplicate UTRs detected across multiple bills")

    # 2. Reversal and Bounced Checks
    for alert in all_alerts:
        content = str(getattr(alert, 'raw_text', getattr(alert, 'raw_content', ''))).lower()
        if any(word in content for word in ["reversed", "reversal", "bounced", "declined", "failed", "unsuccessful"]):
            risk_flags.append("Payment Reversal/Bounce Detected")
            status = "Red"
            requires_human_review = True
            reasons.append("Alert contains failure/reversal keywords")

    for cheque in cheques:
        if getattr(cheque, 'status', '').lower() in ['bounced', 'dishonored', 'returned']:
            risk_flags.append("Bounced Cheque")
            status = "Red"
            requires_human_review = True
            reasons.append("Cheque marked as bounced")

    # 3. Same Amount Multiple Customers / Duplicate Amounts
    amounts = [float(getattr(b, 'amount', getattr(b, 'total_amount', 0))) for b in bills if getattr(b, 'amount', getattr(b, 'total_amount', 0))]
    if len(amounts) != len(set(amounts)):
        risk_flags.append("Duplicate Invoice Amounts")
        status = "Yellow"
        requires_human_review = True
        reasons.append("Multiple invoices have the exact same amount")

    for bill in bills:
        bill_utr = getattr(bill, 'utr_reference', getattr(bill, 'reference_no', None))
        bill_amount = float(getattr(bill, 'amount', getattr(bill, 'total_amount', 0)))
        bill_remaining = float(getattr(bill, 'remaining_amount', bill_amount))
        bill_date = get_date(bill, 'invoice_date')
        
        matching_alerts = [a for a in all_alerts if getattr(a, 'utr_reference', None) == bill_utr] if bill_utr else []
        matching_payments = [p for p in payments if getattr(p, 'bill_id', None) == getattr(bill, 'id', None)]

        # 4. Partial Payments & Split Payments
        total_payment_amount = sum(float(getattr(p, 'amount', 0)) for p in matching_payments)
        total_alert_amount = sum(float(getattr(a, 'amount', 0)) for a in matching_alerts)

        if bill_amount > 0 and total_payment_amount == 0:
            risk_flags.append("Missing Payment Record")
            status = "Yellow"
            requires_human_review = True
            reasons.append("No matching payment records found for this bill")

        if total_payment_amount > 0 and total_payment_amount < bill_amount:
            risk_flags.append("Partial Payment")
            status = "Blue"
            requires_human_review = True
            reasons.append("Payment amount is less than bill amount")

        if len(matching_payments) > 1:
            risk_flags.append("Split Payment")
            status = "Blue"
            requires_human_review = True
            reasons.append("Multiple payment records for single bill")

        # 5. Delayed NEFT / Cross-day matching
        for payment in matching_payments:
            payment_date = get_date(payment, 'payment_date')
            days_diff = (payment_date - bill_date).days
            if days_diff > 1:
                risk_flags.append("Delayed Payment (Cross-day)")
                status = "Yellow"
                requires_human_review = True
                reasons.append(f"Payment received {days_diff} days after invoice")

        # 6. Historical claims (Payment before invoice)
        for payment in matching_payments:
            payment_date = get_date(payment, 'payment_date')
            if (bill_date - payment_date).days > 0:
                risk_flags.append("Historical Payment Claim")
                status = "Purple"
                requires_human_review = True
                reasons.append("Payment date is before invoice date")

        # 7. Delivery before payment
        is_delivered = getattr(bill, 'is_delivered', False)
        if is_delivered and bill_remaining > 0:
            risk_flags.append("Delivery Before Payment")
            status = "Orange"
            requires_human_review = True
            reasons.append("Item delivered but payment is not fully settled")

        # 8. Advance verification
        advance_amount = float(getattr(bill, 'advance_amount', 0))
        advance_status = getattr(bill, 'advance_verification_status', 'UNVERIFIED')
        if advance_amount > 0 and advance_status != 'VERIFIED':
            risk_flags.append("Unverified Advance")
            status = "Blue"
            requires_human_review = True
            reasons.append("Advance payment requires manual verification")

        # 9. Uncertain matches
        if not bill_utr and bill_remaining > 0:
            risk_flags.append("Missing UTR / Unmatched")
            status = "Yellow"
            requires_human_review = True
            reasons.append("No UTR reference provided for pending amount")

    # Dedup risk flags
    risk_flags = list(set(risk_flags))
    
    if not requires_human_review and status == "Green":
        reasons = ["Fully matched and verified"]

    # Failsafe: Never auto-clear uncertain matches
    if len(risk_flags) > 0 and not requires_human_review:
        requires_human_review = True
        status = "Blue"

    return ReconciliationDecision(
        status=status,
        reason=" | ".join(set(reasons)),
        risk_flags=risk_flags,
        requires_human_review=requires_human_review
    )
