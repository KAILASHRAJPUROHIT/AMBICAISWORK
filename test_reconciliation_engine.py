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
    sms_alerts = []

    decision = reconcile_transactions(bills, payments, bank_alerts, sms_alerts, cheques)
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
    sms_alerts = []

    decision = reconcile_transactions(bills, payments, bank_alerts, sms_alerts, cheques)
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
    sms_alerts = []

    decision = reconcile_transactions(bills, payments, bank_alerts, sms_alerts, cheques)
    assert decision.status == "Yellow"
    assert decision.reason == "Missing bank alert"
    assert decision.risk_flags == ["Missing Bank Alert"]
    assert not decision.requires_human_review

def test_cheque_not_cleared():
    bills = [
        {"id": 1, "amount": 100.00, "utr_reference": "ABC123"}
    ]
    bank_alerts = []
    payments = []
    cheques = [
        {"id": 1, "bill_id": 1, "cheque_number": "CHQ123", "bank_name": "BankA", "amount": 100.00, "status": "Blue"}
    ]
    sms_alerts = []

    decision = reconcile_transactions(bills, payments, bank_alerts, sms_alerts, cheques)
    assert decision.status == "Blue"
    assert decision.reason == "Cheque deposited but not cleared"
    assert decision.risk_flags == ["Cheque Not Cleared"]
    assert not decision.requires_human_review

def test_delivery_before_payment():
    bills = [
        {"id": 1, "amount": 100.00, "utr_reference": "ABC123"}
    ]
    bank_alerts = []
    payments = [
        {"id": 1, "bill_id": 1, "amount": 100.00, "mode": "NEFT", "received_at": "2023-04-01T10:00:00Z"}
    ]
    cheques = []
    sms_alerts = []

    decision = reconcile_transactions(bills, payments, bank_alerts, sms_alerts, cheques)
    assert decision.status == "Orange"
    assert decision.reason == "Delivery before payment"
    assert decision.risk_flags == ["Delivery Before Payment"]
    assert not decision.requires_human_review

def test_duplicate_amount():
    bills = [
        {"id": 1, "amount": 100.00, "utr_reference": "ABC123"},
        {"id": 2, "amount": 100.00, "utr_reference": "DEF456"}
    ]
    bank_alerts = []
    payments = [
        {"id": 1, "bill_id": 1, "amount": 100.00, "utr_reference": "ABC123"},
        {"id": 2, "bill_id": 2, "amount": 100.00, "utr_reference": "DEF456"}
    ]
    cheques = []
    sms_alerts = []

    decision = reconcile_transactions(bills, payments, bank_alerts, sms_alerts, cheques)
    assert decision.status == "Red"
    assert decision.reason == "Duplicate UTR or Same amount multiple bills"
    assert decision.risk_flags == ["Duplicate UTR", "Multiple Bills"]
    assert decision.requires_human_review

def test_bounced_cheque():
    bills = [
        {"id": 1, "amount": 100.00, "utr_reference": "ABC123"}
    ]
    bank_alerts = []
    payments = []
    cheques = [
        {"id": 1, "bill_id": 1, "cheque_number": "CHQ123", "bank_name": "BankA", "amount": 100.00, "status": "Red"}
    ]
    sms_alerts = []

    decision = reconcile_transactions(bills, payments, bank_alerts, sms_alerts, cheques)
    assert decision.status == "Red"
    assert decision.reason == "Any mismatch"
    assert decision.risk_flags == ["Bounced Cheque"]
    assert decision.requires_human_review

def test_delayed_neft():
    bills = [
        {"id": 1, "amount": 100.00, "utr_reference": "ABC123"}
    ]
    bank_alerts = []
    payments = [
        {"id": 1, "bill_id": 1, "amount": 100.00, "mode": "NEFT", "received_at": "2023-04-05T10:00:00Z"}
    ]
    cheques = []
    sms_alerts = []

    decision = reconcile_transactions(bills, payments, bank_alerts, sms_alerts, cheques)
    assert decision.status == "Orange"
    assert decision.reason == "Delivery before payment"
    assert decision.risk_flags == ["Delayed NEFT"]
    assert not decision.requires_human_review

def test_split_payment():
    bills = [
        {"id": 1, "amount": 200.00, "utr_reference": "ABC123"}
    ]
    bank_alerts = []
    payments = [
        {"id": 1, "bill_id": 1, "amount": 100.00, "utr_reference": "ABC123"},
        {"id": 2, "bill_id": 1, "amount": 100.00, "utr_reference": "DEF456"}
    ]
    cheques = []
    sms_alerts = []

    decision = reconcile_transactions(bills, payments, bank_alerts, sms_alerts, cheques)
    assert decision.status == "Red"
    assert decision.reason == "Any mismatch"
    assert decision.risk_flags == ["Split Payment"]
    assert decision.requires_human_review
