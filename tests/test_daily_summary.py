import pytest
from backend.daily_summary import generate_daily_summary
from backend.schemas import (
    ReconciliationDecision, 
    ManagedReviewItem, 
    OwnerEscalationRecord
)

def test_empty_summary():
    summary = generate_daily_summary([], [], [])
    assert summary.processed_count == 0
    assert summary.open_reviews == 0
    assert summary.escalated_reviews == 0
    assert summary.resolved_reviews == 0
    assert summary.high_risk_count == 0
    assert summary.critical_risk_count == 0
    assert summary.generated_at is not None

def test_mixed_review_statuses():
    decisions = [
        ReconciliationDecision(status="Green", reason="test", risk_flags=[], requires_human_review=False)
    ]
    reviews = [
        ManagedReviewItem(review_id="1", entity_type="bill", entity_id="1", queue_type="Q1", assigned_role="R1", escalation_required=False, status="OPEN", reason="test", created_at="2026"),
        ManagedReviewItem(review_id="2", entity_type="bill", entity_id="2", queue_type="Q1", assigned_role="R1", escalation_required=False, status="IN_REVIEW", reason="test", created_at="2026"),
        ManagedReviewItem(review_id="3", entity_type="bill", entity_id="3", queue_type="Q1", assigned_role="R1", escalation_required=False, status="RESOLVED", reason="test", created_at="2026"),
        ManagedReviewItem(review_id="4", entity_type="bill", entity_id="4", queue_type="Q1", assigned_role="R1", escalation_required=True, status="ESCALATED", reason="test", created_at="2026"),
    ]
    
    summary = generate_daily_summary(decisions, reviews, [])
    
    assert summary.processed_count == 1
    assert summary.open_reviews == 1
    assert summary.resolved_reviews == 1
    assert summary.escalated_reviews == 1
    # IN_REVIEW is ignored from the specific counts required

def test_high_risk_escalation_count():
    escalations = [
        OwnerEscalationRecord(escalation_id="1", review_id="1", escalation_reason="Dup", severity="HIGH", owner_notified=False, created_at="2026"),
        OwnerEscalationRecord(escalation_id="2", review_id="2", escalation_reason="Other", severity="MEDIUM", owner_notified=False, created_at="2026"),
        OwnerEscalationRecord(escalation_id="3", review_id="3", escalation_reason="Dup2", severity="HIGH", owner_notified=False, created_at="2026"),
    ]
    summary = generate_daily_summary([], [], escalations)
    assert summary.high_risk_count == 2
    assert summary.critical_risk_count == 0

def test_critical_risk_escalation_count():
    escalations = [
        OwnerEscalationRecord(escalation_id="1", review_id="1", escalation_reason="Large", severity="CRITICAL", owner_notified=False, created_at="2026"),
        OwnerEscalationRecord(escalation_id="2", review_id="2", escalation_reason="Large2", severity="CRITICAL", owner_notified=False, created_at="2026"),
    ]
    summary = generate_daily_summary([], [], escalations)
    assert summary.high_risk_count == 0
    assert summary.critical_risk_count == 2

def test_generated_timestamp_exists():
    summary = generate_daily_summary([], [], [])
    assert summary.generated_at is not None
    assert isinstance(summary.generated_at, str)
    assert "T" in summary.generated_at # basic ISO format check
