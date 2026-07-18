from backend.review_queue import route_review
from backend.schemas import ReconciliationDecision
import pytest

def test_duplicate_utr():
    decision = ReconciliationDecision(
        status="Red",
        reason="Duplicate UTR or Same amount multiple bills",
        risk_flags=["Duplicate UTR"],
        requires_human_review=True
    )
    result = route_review(decision.dict())
    assert result["queue_type"] == "OwnerEscalation"
    assert result["assigned_role"] == "Owner"
    assert result["escalation_required"]
    assert result["reason"] == "Duplicate UTR requires owner escalation."

def test_bounced_cheque():
    decision = ReconciliationDecision(
        status="Red",
        reason="Any mismatch",
        risk_flags=["Bounced Cheque"],
        requires_human_review=True
    )
    result = route_review(decision.dict())
    assert result["queue_type"] == "HumanReview"
    assert result["assigned_role"] == "Accountant"
    assert result["escalation_required"]
    assert result["reason"] == "Red always requires human review."

def test_delayed_neft():
    decision = ReconciliationDecision(
        status="Orange",
        reason="Delivery before payment",
        risk_flags=["Delayed NEFT"],
        requires_human_review=False
    )
    result = route_review(decision.dict())
    assert result["queue_type"] == "ApprovalWorkflow"
    assert result["assigned_role"] == "Approver"
    assert not result["escalation_required"]
    assert result["reason"] == "Orange requires approval workflow."

def test_split_payment():
    decision = ReconciliationDecision(
        status="Split Payment",
        reason="Any mismatch",
        risk_flags=["Split Payment"],
        requires_human_review=True
    )
    result = route_review(decision.dict())
    assert result["queue_type"] == "AccountantReview"
    assert result["assigned_role"] == "Accountant"
    assert not result["escalation_required"]
    assert result["reason"] == "Split payments require accountant review."

def test_yellow():
    decision = ReconciliationDecision(
        status="Yellow",
        reason="Missing bank alert",
        risk_flags=["Missing Bank Alert"],
        requires_human_review=False
    )
    result = route_review(decision.dict())
    assert result["queue_type"] == "AccountantReview"
    assert result["assigned_role"] == "Accountant"
    assert not result["escalation_required"]
    assert result["reason"] == "Yellow requires accountant review."
