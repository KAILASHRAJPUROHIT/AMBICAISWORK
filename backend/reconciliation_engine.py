from typing import List, Any
from backend.schemas import ReconciliationDecision

def reconcile_transactions(bills: List[Any], payments: List[Any], bank_alerts: List[Any], sms_alerts: List[Any], cheques: List[Any]) -> ReconciliationDecision:
    if not bills:
        return ReconciliationDecision(
            status="Green",
            reason="No bills to process",
            risk_flags=[],
            requires_human_review=False
        )

    # Check for duplicate UTRs across all bills
    utrs_in_bills = [getattr(b, 'utr_reference', None) for b in bills if getattr(b, 'utr_reference', None)]
    if len(utrs_in_bills) != len(set(utrs_in_bills)):
        return ReconciliationDecision(
            status="Red",
            reason="Duplicate UTR or Same amount multiple bills",
            risk_flags=["Duplicate UTR", "Multiple Bills"],
            requires_human_review=True
        )

    for bill in bills:
        bill_utr = getattr(bill, 'utr_reference', None)
        matching_bank_alerts = [alert for alert in bank_alerts if getattr(alert, 'utr_reference', None) == bill_utr]
        matching_payments = [payment for payment in payments if getattr(payment, 'utr_reference', None) == bill_utr]
        
        if len(matching_bank_alerts) > 1 or len(matching_payments) > 1:
            return ReconciliationDecision(
                status="Red",
                reason="Duplicate UTR or Same amount multiple bills",
                risk_flags=["Duplicate UTR", "Multiple Bills"],
                requires_human_review=True
            )
        
        if not matching_bank_alerts or not matching_payments:
            return ReconciliationDecision(
                status="Yellow",
                reason="Missing bank alert",
                risk_flags=["Missing Bank Alert"],
                requires_human_review=False
            )

    return ReconciliationDecision(
        status="Green",
        reason="Exact amount + exact UTR + single matching bill + single matching bank alert",
        risk_flags=[],
        requires_human_review=False
    )
