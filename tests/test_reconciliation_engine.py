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
    assert decision.reason == "Exact amount + exact UTR + single matching bill + single matching bank alert"
    assert not decision.risk_flags
    assert not decision.requires_human_review

    bills.append(Bill(utr_reference="12345"))
    decision = reconcile_transactions(bills, payments, bank_alerts, sms_alerts, cheques)
    assert decision.status == "Red"
    assert decision.reason == "Duplicate UTR or Same amount multiple bills"
    assert decision.risk_flags == ["Duplicate UTR", "Multiple Bills"]
    assert decision.requires_human_review

    bills = [Bill(utr_reference="12345")]
    payments = []
    decision = reconcile_transactions(bills, payments, bank_alerts, sms_alerts, cheques)
    assert decision.status == "Yellow"
    assert decision.reason == "Missing bank alert"
    assert decision.risk_flags == ["Missing Bank Alert"]
    assert not decision.requires_human_review
