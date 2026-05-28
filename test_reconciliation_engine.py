from backend.reconciliation_engine import reconcile_transactions, ReconciliationDecision
import pytest

def test_exact_match():
    bills = [
        {"id": 1, "amount": 100.00, "utr_reference": "ABC123"}
    ]
    bank_alerts = [
        {"id": 1, "amount": 100.00, "utr_reference": "ABC123"}
    ]
    payments = [
        {"id": 1, "amount": 100.00, "utr_reference": "ABC123"}
    ]
    cheques = []

    decision = reconcile_transactions(bills, bank_alerts, payments, cheques)
    assert decision.status == "Green"
    assert decision.reason == "Exact amount + exact UTR + single matching bill + single matching bank alert"
    assert not decision.risk_flags
    assert not decision.requires_human_review

def test_duplicate_utr():
    bills = [
        {"id": 1, "amount": 100.00, "utr_reference": "ABC123"},
        {"id": 2, "amount": 100.00, "utr_reference": "ABC123"}
    ]
    bank_alerts = []
    payments = []
    cheques = []

    decision = reconcile_transactions(bills, bank_alerts, payments, cheques)
    assert decision.status == "Red"
    assert decision.reason == "Duplicate UTR or Same amount multiple bills"
    assert decision.risk_flags == ["Duplicate UTR"]
    assert decision.requires_human_review

def test_missing_bank_alert():
    bills = [
        {"id": 1, "amount": 100.00, "utr_reference": "ABC123"}
    ]
    bank_alerts = []
    payments = []
    cheques = []

    decision = reconcile_transactions(bills, bank_alerts, payments, cheques)
    assert decision.status == "Yellow"
    assert decision.reason == "Missing bank alert"
    assert decision.risk_flags == ["Missing Bank Alert"]
    assert not decision.requires_human_review
