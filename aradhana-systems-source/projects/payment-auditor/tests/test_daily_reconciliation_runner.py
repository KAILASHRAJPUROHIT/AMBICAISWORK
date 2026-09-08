import pytest
from unittest.mock import patch
from backend.daily_reconciliation_runner import run_daily_reconciliation
from backend.schemas import NormalizedBankAlert

@pytest.fixture
def mock_alert():
    return NormalizedBankAlert(
        amount=500.0,
        utr_reference="UTR123",
        transaction_date="15/05/2026",
        sender_bank="HDFC",
        source_type="SMS",
        raw_content="Raw SMS content"
    )

@patch("backend.daily_reconciliation_runner.process_bank_alert")
def test_no_alerts_scenario(mock_process):
    result = run_daily_reconciliation([], [], [], [])
    assert result["processed_count"] == 0
    assert len(result["decisions"]) == 0
    assert len(result["review_routes"]) == 0
    assert len(result["audit_payloads"]) == 0
    mock_process.assert_not_called()

@patch("backend.daily_reconciliation_runner.process_bank_alert")
def test_single_alert(mock_process, mock_alert):
    mock_process.return_value = {
        "decision": "Green",
        "review_route": "default",
        "audit_payload": "Payload"
    }
    
    result = run_daily_reconciliation([], [], [], [mock_alert])
    assert result["processed_count"] == 1
    assert result["decisions"] == ["Green"]
    mock_process.assert_called_once_with(bank_alert=mock_alert, bills=[], payments=[], cheques=[])

@patch("backend.daily_reconciliation_runner.process_bank_alert")
def test_multiple_alerts(mock_process, mock_alert):
    mock_process.side_effect = [
        {"decision": "Green", "review_route": "default", "audit_payload": "Payload1"},
        {"decision": "Yellow", "review_route": "AccountantReview", "audit_payload": "Payload2"}
    ]
    
    alert2 = NormalizedBankAlert(
        amount=1000.0, 
        utr_reference="UTR456", 
        transaction_date="16/05/2026", 
        sender_bank="SBI", 
        source_type="EMAIL", 
        raw_content="Raw Email"
    )
    
    result = run_daily_reconciliation([], [], [], [mock_alert, alert2])
    assert result["processed_count"] == 2
    assert result["decisions"] == ["Green", "Yellow"]
    assert result["review_routes"] == ["default", "AccountantReview"]
    assert mock_process.call_count == 2

@patch("backend.daily_reconciliation_runner.process_bank_alert")
def test_duplicate_utr_scenario(mock_process, mock_alert):
    mock_process.return_value = {
        "decision": "Red",
        "review_route": "OwnerEscalation",
        "audit_payload": "Payload"
    }
    
    result = run_daily_reconciliation([], [], [], [mock_alert])
    assert result["processed_count"] == 1
    assert result["decisions"][0] == "Red"
    assert result["review_routes"][0] == "OwnerEscalation"
    mock_process.assert_called_once()

@patch("backend.daily_reconciliation_runner.process_bank_alert")
def test_split_payment_scenario(mock_process, mock_alert):
    mock_process.return_value = {
        "decision": "Split Payment",
        "review_route": "AccountantReview",
        "audit_payload": "Payload"
    }
    
    result = run_daily_reconciliation([], [], [], [mock_alert])
    assert result["processed_count"] == 1
    assert result["decisions"][0] == "Split Payment"
    assert result["review_routes"][0] == "AccountantReview"
    mock_process.assert_called_once()
