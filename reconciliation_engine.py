from typing import List, Dict, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.models import Bill, BankAlert, Payment, Cheque, SMSAlert

class ReconciliationDecision(BaseModel):
    status: str
    reason: str
    risk_flags: List[str]
    requires_human_review: bool

def reconcile_transactions(bills: List[Bill], payments: List[Payment], bank_alerts: List[BankAlert], sms_alerts: List[SMSAlert], cheques: List[Cheque]) -> ReconciliationDecision:
    decisions = []

    for bill in bills:
        matching_bank_alerts = [alert for alert in bank_alerts if alert.utr_reference == bill.utr_reference]
        matching_payments = [payment for payment in payments if payment.utr_reference == bill.utr_reference]

        if len(matching_bank_alerts) == 1 and len(matching_payments) == 1:
            decisions.append({
                "status": "Green",
                "reason": "Exact amount + exact UTR + single matching bill + single matching bank alert",
                "risk_flags": [],
                "requires_human_review": False
            })
        elif len(matching_bank_alerts) > 1 or len(matching_payments) > 1:
            decisions.append({
                "status": "Red",
                "reason": "Duplicate UTR or Same amount multiple bills",
                "risk_flags": ["Duplicate UTR", "Multiple Bills"],
                "requires_human_review": True
            })
        elif not matching_bank_alerts:
            decisions.append({
                "status": "Yellow",
                "reason": "Missing bank alert",
                "risk_flags": ["Missing Bank Alert"],
                "requires_human_review": False
            })

    return ReconciliationDecision(
        status="Green" if all(decision["status"] == "Green" for decision in decisions) else "Red",
        reason=", ".join([decision["reason"] for decision in decisions]),
        risk_flags=[flag for decision in decisions for flag in decision["risk_flags"]],
        requires_human_review=any(decision["requires_human_review"] for decision in decisions)
    )
