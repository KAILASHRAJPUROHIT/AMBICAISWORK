from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.alert_framework import (
    developer_login_failure_alert,
    developer_system_failure_alert,
    developer_tamper_alert,
    owner_accountant_overdue_alerts,
    owner_uncleared_payment_alerts,
    scan_login_failure_alerts,
)
from backend.database import Base
from backend.models import AlertRecord, AuditLog, Bill, LoginLog, Payment
from backend import email_notifier


def make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    return db


def sent_subjects(mock_send_email):
    return [call.args[1] for call in mock_send_email.call_args_list]


def test_developer_login_failure_alert():
    db = make_db()
    try:
        with patch("backend.alert_framework.send_email", return_value=True) as mock_send:
            alert = developer_login_failure_alert(db, "OWNER-01", {"reason": "bad_password"})

        assert alert.status == "sent"
        assert alert.subject.startswith("DEVELOPERS ALERT")
        assert "login_failures" in alert.subject
        assert sent_subjects(mock_send)[0].startswith("DEVELOPERS ALERT")
    finally:
        db.close()


def test_scan_login_failures_generates_developer_alert():
    db = make_db()
    try:
        db.add(LoginLog(employee_id="STAFF-01", event_type="PASSWORD_FAILED", ip_address="127.0.0.1"))
        db.commit()

        with patch("backend.alert_framework.send_email", return_value=True) as mock_send:
            alerts = scan_login_failure_alerts(db, now=datetime(2026, 6, 6, 10, 0))

        assert len(alerts) == 1
        assert alerts[0].category == "login_failures"
        assert mock_send.call_args.args[1].startswith("DEVELOPERS ALERT")
    finally:
        db.close()


def test_developer_system_failure_alert():
    db = make_db()
    try:
        with patch("backend.alert_framework.send_email", return_value=True) as mock_send:
            alert = developer_system_failure_alert(db, "pdf-worker", {"error": "worker crashed"})

        assert alert.status == "sent"
        assert alert.category == "system_failures"
        assert mock_send.call_args.args[1].startswith("DEVELOPERS ALERT")
    finally:
        db.close()


def test_developer_tamper_alert():
    db = make_db()
    try:
        with patch("backend.alert_framework.send_email", return_value=True) as mock_send:
            alert = developer_tamper_alert(db, "audit-log-gap", {"entity": "audit_logs"})

        assert alert.status == "sent"
        assert alert.category == "tamper_alerts"
        assert mock_send.call_args.args[1].startswith("DEVELOPERS ALERT")
    finally:
        db.close()


def test_owner_48_hour_accountant_overdue_alert():
    db = make_db()
    try:
        now = datetime(2026, 6, 6, 12, 0)
        bill = Bill(
            bill_number="OVERDUE-48",
            customer_name="Review Customer",
            amount=1000,
            status="Yellow",
            review_required=1,
            is_test_data=False,
            created_at=now - timedelta(hours=49),
        )
        db.add(bill)
        db.commit()

        with patch("backend.alert_framework.send_email", return_value=True) as mock_send:
            alerts = owner_accountant_overdue_alerts(db, now=now)

        assert len(alerts) == 1
        assert alerts[0].category == "accountant_overdue_48h"
        assert alerts[0].subject.startswith("OWNER ALERT")
        assert mock_send.call_args.args[1].startswith("OWNER ALERT")
    finally:
        db.close()


def test_owner_7_day_uncleared_payment_alert():
    db = make_db()
    try:
        now = datetime(2026, 6, 6, 12, 0)
        bill = Bill(bill_number="PAY-7D", amount=1000, status="Yellow", is_test_data=False, created_at=now)
        db.add(bill)
        db.flush()
        payment = Payment(
            bill_id=bill.id,
            amount=1000,
            mode="UPI",
            status="Yellow",
            created_at=now - timedelta(days=8),
        )
        db.add(payment)
        db.commit()

        with patch("backend.alert_framework.send_email", return_value=True) as mock_send:
            alerts = owner_uncleared_payment_alerts(db, now=now)

        assert len(alerts) == 1
        assert alerts[0].category == "uncleared_payment_7d"
        assert alerts[0].subject.startswith("OWNER ALERT")
        assert mock_send.call_args.args[1].startswith("OWNER ALERT")
    finally:
        db.close()


def test_deduplication_prevents_repeat_spam_and_tracks_suppressed_record():
    db = make_db()
    try:
        now = datetime(2026, 6, 6, 12, 0)
        with patch("backend.alert_framework.send_email", return_value=True) as mock_send:
            first = developer_system_failure_alert(db, "backend", {"error": "first"})
            second = developer_system_failure_alert(db, "backend", {"error": "repeat"})

        assert first.status == "sent"
        assert second.status == "suppressed"
        assert mock_send.call_count == 1
        records = db.query(AlertRecord).all()
        assert {record.status for record in records} == {"sent", "suppressed"}
    finally:
        db.close()


def test_alert_generation_writes_immutable_audit_log():
    db = make_db()
    try:
        with patch("backend.alert_framework.send_email", return_value=True):
            alert = developer_tamper_alert(db, "settings-change", {"field": "EMAIL_PASSWORD"})

        actions = [log.action for log in db.query(AuditLog).all()]
        assert "ALERT_GENERATED" in actions
        assert "ALERT_SENT" in actions
        audit_payload = " ".join(log.metadata_json or "" for log in db.query(AuditLog).all())
        assert alert.dedupe_key in audit_payload
    finally:
        db.close()


def test_otp_email_unaffected_by_new_alert_framework():
    with patch("backend.email_notifier.send_email", return_value=True) as mock_send:
        assert email_notifier.send_otp_email("owner@example.com", "123456") is True

    mock_send.assert_called_once()
    assert mock_send.call_args.args[1].startswith("OTP:")
