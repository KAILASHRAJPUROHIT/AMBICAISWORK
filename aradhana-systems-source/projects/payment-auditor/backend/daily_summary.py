from typing import List
from datetime import datetime
from backend.schemas import (
    ReconciliationDecision, 
    ManagedReviewItem, 
    OwnerEscalationRecord, 
    DailySummary
)

def generate_daily_summary(
    decisions: List[ReconciliationDecision],
    review_items: List[ManagedReviewItem],
    escalations: List[OwnerEscalationRecord]
) -> DailySummary:
    
    processed_count = len(decisions)
    
    open_reviews = sum(1 for r in review_items if r.status == "OPEN")
    escalated_reviews = sum(1 for r in review_items if r.status == "ESCALATED")
    resolved_reviews = sum(1 for r in review_items if r.status == "RESOLVED")
    
    high_risk_count = sum(1 for e in escalations if e.severity == "HIGH")
    critical_risk_count = sum(1 for e in escalations if e.severity == "CRITICAL")
    
    notes = f"Daily summary completed. Processed: {processed_count}."
    
    return DailySummary(
        generated_at=datetime.utcnow().isoformat(),
        processed_count=processed_count,
        open_reviews=open_reviews,
        escalated_reviews=escalated_reviews,
        resolved_reviews=resolved_reviews,
        high_risk_count=high_risk_count,
        critical_risk_count=critical_risk_count,
        summary_notes=notes
    )
