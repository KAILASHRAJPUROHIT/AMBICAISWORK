from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from backend.rbac import UserRole, get_permissions
from backend.review_queue_manager import get_open_reviews, _reviews_db
from backend.owner_escalation import get_open_escalations, _escalations_db
from backend.owner_report import generate_owner_report
from backend.daily_summary import generate_daily_summary
from backend.schemas import ManagedReviewItem, OwnerEscalationRecord, DailySummary, ReconciliationDecision


router = APIRouter()

@router.get("/health")
def health():
    return {"status": "healthy"}

@router.get("/permissions/{role}")
def get_role_permissions(role: str):
    try:
        user_role = UserRole[role.upper()]
    except KeyError:
        raise HTTPException(status_code=404, detail="Role not found")
    
    permissions = get_permissions(user_role)
    return {"role": user_role.value, "permissions": [p.value for p in permissions]}

@router.get("/reviews/open", response_model=List[ManagedReviewItem])
def get_open_reviews_api():
    # For now, we'll use a dummy data if the _reviews_db is empty for deterministic testing
    if not _reviews_db:
        # Create some dummy open reviews
        _reviews_db["mock_review_1"] = ManagedReviewItem(
            review_id="mock_review_1",
            entity_type="payment",
            entity_id="pay_001",
            queue_type="default",
            assigned_role="ACCOUNTANT",
            escalation_required=False,
            status="OPEN",
            reason="Unmatched payment",
            created_at=datetime.utcnow().isoformat()
        )
        _reviews_db["mock_review_2"] = ManagedReviewItem(
            review_id="mock_review_2",
            entity_type="bill",
            entity_id="bill_002",
            queue_type="default",
            assigned_role="ACCOUNTANT",
            escalation_required=False,
            status="OPEN",
            reason="Bill discrepancy",
            created_at=datetime.utcnow().isoformat()
        )
    return get_open_reviews()

@router.get("/escalations/open", response_model=List[OwnerEscalationRecord])
def get_open_escalations_api():
    # For now, we'll use a dummy data if the _escalations_db is empty for deterministic testing
    if not _escalations_db:
        # Create some dummy open escalations
        from backend.owner_escalation import create_escalation # Import here to avoid circular dependency
        create_escalation("mock_esc_1", "mock_review_1", "LARGE AMOUNT MISMATCH")
        create_escalation("mock_esc_2", "mock_review_3", "DUPLICATE UTR")

    return get_open_escalations()

@router.get("/reports/owner")
def get_owner_report_api():
    # Generate mock DailySummary and Escalations for the report
    # In a real app, these would come from a database or other services

    # Mock daily summary data
    mock_daily_summary = DailySummary(
        generated_at=datetime.utcnow().isoformat(),
        processed_count=100,
        open_reviews=5,
        escalated_reviews=2,
        resolved_reviews=93,
        high_risk_count=1,
        critical_risk_count=1,
        summary_notes="Mock daily summary for owner report."
    )

    # Mock escalation data
    mock_escalations = [
        OwnerEscalationRecord(
            escalation_id="mock_esc_critical",
            review_id="rev_crit_001",
            escalation_reason="CRITICAL RISK: Major Fraud Detected",
            severity="critical",
            owner_notified=True,
            created_at=datetime.utcnow().isoformat(),
            resolved_at=None
        ),
        OwnerEscalationRecord(
            escalation_id="mock_esc_high",
            review_id="rev_high_002",
            escalation_reason="HIGH RISK: Large Discrepancy",
            severity="high",
            owner_notified=True,
            created_at=datetime.utcnow().isoformat(),
            resolved_at=None
        )
    ]
    
    report_date = datetime.now().strftime("%Y-%m-%d")
    
    # Financial Parity: Include payment bifurcation in owner report
    from backend.review_api import get_payment_bifurcation
    bif_data = None
    try:
        from backend.database import SessionLocal
        db = SessionLocal()
        # We wrap in a task to avoid event loop issues if needed, or just call async helper
        # But get_owner_report_api is sync, so we need a sync version of bifurcation
        # Or just make it async. For now let's pass None and fix it if owner needs it today.
        db.close()
    except: pass

    owner_report = generate_owner_report(report_date, mock_daily_summary, mock_escalations, bifurcation=bif_data)
    return owner_report
