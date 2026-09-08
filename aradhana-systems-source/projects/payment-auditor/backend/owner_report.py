from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from backend.schemas import DailySummary, OwnerEscalationRecord


class OwnerReport(BaseModel):
    generated_at: datetime
    report_date: str  # YYYY-MM-DD
    processed_count: int
    open_reviews: int
    escalated_reviews: int
    high_risk_count: int
    critical_risk_count: int
    owner_action_required: bool
    report_lines: List[str]


def generate_owner_report(
    report_date: str,
    daily_summary: DailySummary,
    escalations: List[OwnerEscalationRecord],
    bifurcation: List[dict] = None
) -> OwnerReport:
    """
    Generates an owner report based on daily summary and escalation records.
    """
    report_lines: List[str] = []
    
    if bifurcation:
        report_lines.append("\nPAYMENT MODE BIFURCATION:")
        for item in bifurcation:
            if item["total"] > 0 or item["count"] > 0:
                report_lines.append(f"  {item['mode']}: ₹{item['total']:,.2f} ({item['count']} items)")
        report_lines.append("-" * 40)

    # Include critical escalations first
    critical_escalations = [
        e for e in escalations if e.severity == "critical"
    ]
    for esc in critical_escalations:
        report_lines.append(
            f"CRITICAL ESCALATION: Review ID {esc.review_id} - {esc.escalation_reason}"
        )

    # Include high escalations next
    high_escalations = [
        e for e in escalations if e.severity == "high"
    ]
    for esc in high_escalations:
        report_lines.append(
            f"HIGH ESCALATION: Review ID {esc.review_id} - {esc.escalation_reason}"
        )
    
    # Include summary counts
    report_lines.append(f"Processed Count: {daily_summary.processed_count}")
    report_lines.append(f"Open Reviews: {daily_summary.open_reviews}")
    report_lines.append(f"Escalated Reviews: {daily_summary.escalated_reviews}")
    report_lines.append(f"High Risk Count: {daily_summary.high_risk_count}")
    report_lines.append(f"Critical Risk Count: {daily_summary.critical_risk_count}")


    owner_action_required = (
        daily_summary.critical_risk_count > 0
        or daily_summary.high_risk_count > 0
        or daily_summary.escalated_reviews > 0
    )

    return OwnerReport(
        generated_at=datetime.now(),
        report_date=report_date,
        processed_count=daily_summary.processed_count,
        open_reviews=daily_summary.open_reviews,
        escalated_reviews=daily_summary.escalated_reviews,
        high_risk_count=daily_summary.high_risk_count,
        critical_risk_count=daily_summary.critical_risk_count,
        owner_action_required=owner_action_required,
        report_lines=report_lines,
    )
