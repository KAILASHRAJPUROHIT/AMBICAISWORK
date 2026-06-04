from backend.reconciliation_engine import reconcile_transactions
from backend.schemas import ReconciliationDecision
import pytest

class Bill:
    def __init__(self, utr_reference):
        self.utr_reference = utr_reference

class Payment:
    def __init__(self, utr_reference):
        self.utr_reference = utr_reference

class BankAlert:
    def __init__(self, utr_reference):
        self.utr_reference = utr_reference

def test_reconcile_transactions():
    bills = [Bill(utr_reference="12345")]
    payments = [Payment(utr_reference="12345")]
    bank_alerts = [BankAlert(utr_reference="12345")]
    sms_alerts = []
    cheques = []

    decision = reconcile_transactions(bills, payments, bank_alerts, sms_alerts, cheques)
    assert decision.status == "Green"
    assert decision.reason == "Fully matched and verified"
    assert not decision.risk_flags
    assert not decision.requires_human_review

    bills.append(Bill(utr_reference="12345"))
    decision = reconcile_transactions(bills, payments, bank_alerts, sms_alerts, cheques)
    assert decision.status == "Red"
    assert decision.reason == "Duplicate UTRs detected across multiple bills"
    assert decision.risk_flags == ["Duplicate UTR in Bills"]
    assert decision.requires_human_review

    bills = [Bill(utr_reference="12345")]
    payments = []
    # Add id and total_amount to mock Bill for new engine logic
    bills[0].id = 1
    bills[0].total_amount = 100.0
    bills[0].remaining_amount = 100.0
    
    decision = reconcile_transactions(bills, payments, bank_alerts, sms_alerts, cheques)
    assert decision.status == "Yellow"
    assert "Missing UTR / Unmatched" in decision.risk_flags or "Missing Payment Record" in decision.risk_flags

