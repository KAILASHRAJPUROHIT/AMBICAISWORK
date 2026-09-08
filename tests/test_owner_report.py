from datetime import datetime
from backend.owner_report import generate_owner_report
from backend.schemas import DailySummary, OwnerEscalationRecord


def create_daily_summary(
    processed_count: int = 0,
    open_reviews: int = 0,
    escalated_reviews: int = 0,
    resolved_reviews: int = 0,
    high_risk_count: int = 0,
    critical_risk_count: int = 0,
    summary_notes: str = "",
) -> DailySummary:
    return DailySummary(
        generated_at=datetime.now().isoformat(),
        processed_count=processed_count,
        open_reviews=open_reviews,
        escalated_reviews=escalated_reviews,
        resolved_reviews=resolved_reviews,
        high_risk_count=high_risk_count,
        critical_risk_count=critical_risk_count,
        summary_notes=summary_notes,
    )


def create_escalation_record(
    review_id: str, severity: str, escalation_reason: str
) -> OwnerEscalationRecord:
    return OwnerEscalationRecord(
        escalation_id=f"esc-{review_id}",
        review_id=review_id,
        escalation_reason=escalation_reason,
        severity=severity,
        owner_notified=True,
        created_at=datetime.now().isoformat(),
        resolved_at=None,
    )


def test_empty_clean_report():
    report_date = "2024-05-30"
    daily_summary = create_daily_summary()
    escalations = []
    report = generate_owner_report(report_date, daily_summary, escalations)

    assert report.report_date == report_date
    assert report.processed_count == 0
    assert report.open_reviews == 0
    assert report.escalated_reviews == 0
    assert report.high_risk_count == 0
    assert report.critical_risk_count == 0
    assert not report.owner_action_required
    assert "Processed Count: 0" in report.report_lines
    assert "Open Reviews: 0" in report.report_lines
    assert "Escalated Reviews: 0" in report.report_lines
    assert "High Risk Count: 0" in report.report_lines
    assert "Critical Risk Count: 0" in report.report_lines
    assert len(report.report_lines) == 5  # Only summary counts


def test_report_with_high_risk_escalation():
    report_date = "2024-05-30"
    daily_summary = create_daily_summary(high_risk_count=1)
    escalations = [
        create_escalation_record("R001", "high", "Unusual large transaction")
    ]
    report = generate_owner_report(report_date, daily_summary, escalations)

    assert report.high_risk_count == 1
    assert report.owner_action_required
    assert "HIGH ESCALATION: Review ID R001 - Unusual large transaction" in report.report_lines
    assert report.report_lines[0] == "HIGH ESCALATION: Review ID R001 - Unusual large transaction"
    assert len(report.report_lines) == 6  # 1 high escalation + 5 summary lines


def test_report_with_critical_risk_escalation():
    report_date = "2024-05-30"
    daily_summary = create_daily_summary(critical_risk_count=1)
    escalations = [
        create_escalation_record("R002", "critical", "Potential fraud detected")
    ]
    report = generate_owner_report(report_date, daily_summary, escalations)

    assert report.critical_risk_count == 1
    assert report.owner_action_required
    assert "CRITICAL ESCALATION: Review ID R002 - Potential fraud detected" in report.report_lines
    assert report.report_lines[0] == "CRITICAL ESCALATION: Review ID R002 - Potential fraud detected"
    assert len(report.report_lines) == 6  # 1 critical escalation + 5 summary lines


def test_owner_action_required_true():
    # Case 1: critical_risk_count > 0
    daily_summary_critical = create_daily_summary(critical_risk_count=1)
    report_critical = generate_owner_report("2024-05-30", daily_summary_critical, [])
    assert report_critical.owner_action_required

    # Case 2: high_risk_count > 0
    daily_summary_high = create_daily_summary(high_risk_count=1)
    report_high = generate_owner_report("2024-05-30", daily_summary_high, [])
    assert report_high.owner_action_required

    # Case 3: escalated_reviews > 0
    daily_summary_escalated = create_daily_summary(escalated_reviews=1)
    report_escalated = generate_owner_report("2024-05-30", daily_summary_escalated, [])
    assert report_escalated.owner_action_required

    # Case 4: No action required
    daily_summary_clean = create_daily_summary()
    report_clean = generate_owner_report("2024-05-30", daily_summary_clean, [])
    assert not report_clean.owner_action_required


def test_report_lines_generated():
    report_date = "2024-05-30"
    daily_summary = create_daily_summary(
        processed_count=100, open_reviews=5, escalated_reviews=2,
        high_risk_count=1, critical_risk_count=1
    )
    escalations = [
        create_escalation_record("R003", "high", "Suspicious activity"),
        create_escalation_record("R004", "critical", "Account compromise attempt"),
    ]
    report = generate_owner_report(report_date, daily_summary, escalations)

    assert "CRITICAL ESCALATION: Review ID R004 - Account compromise attempt" in report.report_lines
    assert "HIGH ESCALATION: Review ID R003 - Suspicious activity" in report.report_lines
    assert "Processed Count: 100" in report.report_lines
    assert "Open Reviews: 5" in report.report_lines
    assert "Escalated Reviews: 2" in report.report_lines
    assert "High Risk Count: 1" in report.report_lines
    assert "Critical Risk Count: 1" in report.report_lines


def test_critical_appears_before_high_in_report_lines():
    report_date = "2024-05-30"
    daily_summary = create_daily_summary(
        high_risk_count=1, critical_risk_count=1
    )
    escalations = [
        create_escalation_record("R005", "high", "Minor anomaly"),
        create_escalation_record("R006", "critical", "Major security breach"),
    ]
    report = generate_owner_report(report_date, daily_summary, escalations)

    critical_line_index = -1
    high_line_index = -1

    for i, line in enumerate(report.report_lines):
        if "CRITICAL ESCALATION: Review ID R006" in line:
            critical_line_index = i
        if "HIGH ESCALATION: Review ID R005" in line:
            high_line_index = i
    
    assert critical_line_index != -1
    assert high_line_index != -1
    assert critical_line_index < high_line_index
