import pytest
from unittest.mock import patch
from backend.schemas import NormalizedBankAlert, ReconciliationDecision, AuditLogCreate
from backend.reconciliation_orchestrator import process_bank_alert

@pytest.fixture
def mock_alert():
    return NormalizedBankAlert(
        amount=100.0,
        utr_reference="12345",
        transaction_date="01/01/2026",
        sender_bank="SBI",
        source_type="EMAIL",
        raw_content="Raw Data"
    )

@patch('backend.reconciliation_orchestrator.reconcile_transactions')
def test_exact_match_path(mock_reconcile, mock_alert):
    mock_reconcile.return_value = ReconciliationDecision(
        status="Green",
        reason="Exact match",
        risk_flags=[],
        requires_human_review=False
    )
    
    result = process_bank_alert(mock_alert, [], [], [])
    
    assert result["decision"].status == "Green"
    assert result["review_route"]["queue_type"] == "default"
    assert isinstance(result["audit_payload"], AuditLogCreate)
    assert result["audit_payload"].new_status == "Green"
    mock_reconcile.assert_called_once()

@patch('backend.reconciliation_orchestrator.reconcile_transactions')
def test_duplicate_utr_path(mock_reconcile, mock_alert):
    mock_reconcile.return_value = ReconciliationDecision(
        status="Red",
        reason="Duplicate UTR",
        risk_flags=["Duplicate UTR"],
        requires_human_review=True
    )
    
    result = process_bank_alert(mock_alert, [], [], [])
    
    assert result["decision"].status == "Red"
    assert result["review_route"]["escalation_required"] is True
    assert result["review_route"]["assigned_role"] == "Owner"
    assert result["review_route"]["queue_type"] == "OwnerEscalation"
    assert result["audit_payload"].new_status == "Red"

@patch('backend.reconciliation_orchestrator.reconcile_transactions')
def test_split_payment_path(mock_reconcile, mock_alert):
    mock_reconcile.return_value = ReconciliationDecision(
        status="Split Payment",
        reason="Split",
        risk_flags=["Split Payment"],
        requires_human_review=True
    )
    
    result = process_bank_alert(mock_alert, [], [], [])
    
    assert result["decision"].status == "Split Payment"
    assert result["review_route"]["queue_type"] == "AccountantReview"
    assert result["audit_payload"].new_status == "Split Payment"

@patch('backend.reconciliation_orchestrator.reconcile_transactions')
def test_cheque_pending_path(mock_reconcile, mock_alert):
    mock_reconcile.return_value = ReconciliationDecision(
        status="Blue",
        reason="Pending cheque",
        risk_flags=[],
        requires_human_review=False
    )
    
    result = process_bank_alert(mock_alert, [], [], [])
    
    assert result["decision"].status == "Blue"
    # Falls through to defaults since it's unhandled in route_review directly
    assert result["review_route"]["queue_type"] == "default"
    assert result["audit_payload"].new_status == "Blue"

@patch('backend.reconciliation_orchestrator.reconcile_transactions')
def test_owner_escalation_path(mock_reconcile, mock_alert):
    # Tests a different variant or same as duplicate UTR that leads to owner escalation
    mock_reconcile.return_value = ReconciliationDecision(
        status="Red",
        reason="Large Mismatch",
        risk_flags=["Duplicate UTR"],
        requires_human_review=True
    )
    
    result = process_bank_alert(mock_alert, [], [], [])
    
    assert result["review_route"]["escalation_required"] is True
    assert result["review_route"]["queue_type"] == "OwnerEscalation"
    assert result["audit_payload"].new_status == "Red"
