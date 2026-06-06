import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.email_notifier import SECURITY_ALERT_EMAIL, send_email
from backend.models import AlertRecord, AuditLog, Bill, LoginLog, Payment


DEVELOPER_PREFIX = "DEVELOPERS ALERT"
OWNER_PREFIX = "OWNER ALERT"

DEVELOPER_CATEGORIES = {
    "login_failures",
    "system_failures",
    "tamper_alerts",
}

OWNER_CATEGORIES = {
    "accountant_overdue_48h",
    "uncleared_payment_7d",
}


def developer_alert_email() -> str:
    return os.getenv("DEVELOPER_ALERT_EMAIL", SECURITY_ALERT_EMAIL)


def owner_alert_email() -> str:
    return os.getenv("OWNER_ALERT_EMAIL", SECURITY_ALERT_EMAIL)


def _today_key(now: Optional[datetime] = None) -> str:
    return (now or datetime.now()).strftime("%Y-%m-%d")


def _ensure_alert_table(db: Session):
    AlertRecord.__table__.create(bind=db.get_bind(), checkfirst=True)


def _json(data: Dict[str, Any]) -> str:
    return json.dumps(data, default=str, sort_keys=True)


def _subject(prefix: str, category: str, entity_label: str) -> str:
    return f"{prefix}: {category} - {entity_label}"


def _audit(db: Session, action: str, alert: AlertRecord, metadata: Dict[str, Any]):
    db.add(AuditLog(
        entity_type="ALERT",
        entity_id=alert.id or 0,
        action=action,
        old_status=None,
        new_status=alert.status,
        actor="ALERT_FRAMEWORK",
        metadata_json=_json({
            "alert_type": alert.alert_type,
            "category": alert.category,
            "entity_type": alert.entity_type,
            "entity_id": alert.entity_id,
            "dedupe_key": alert.dedupe_key,
            "subject": alert.subject,
            "recipient": alert.recipient,
            **metadata,
        }),
    ))


def _html_body(prefix: str, category: str, entity_label: str, details: Dict[str, Any]) -> str:
    detail_rows = "".join(
        f"<tr><td><b>{key}</b></td><td>{value}</td></tr>"
        for key, value in details.items()
    )
    return f"""
    <html>
      <body style="font-family: sans-serif; color: #222;">
        <h2>{prefix}</h2>
        <p><b>Category:</b> {category}</p>
        <p><b>Entity:</b> {entity_label}</p>
        <table cellpadding="6" cellspacing="0" border="1">{detail_rows}</table>
      </body>
    </html>
    """


def generate_alert(
    db: Session,
    *,
    alert_type: str,
    category: str,
    entity_type: str,
    entity_id: str,
    entity_label: str,
    details: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> AlertRecord:
    _ensure_alert_table(db)
    details = details or {}
    normalized_type = alert_type.upper()
    if normalized_type == "DEVELOPER":
        if category not in DEVELOPER_CATEGORIES:
            raise ValueError(f"Unsupported developer alert category: {category}")
        prefix = DEVELOPER_PREFIX
        recipient = developer_alert_email()
    elif normalized_type == "OWNER":
        if category not in OWNER_CATEGORIES:
            raise ValueError(f"Unsupported owner alert category: {category}")
        prefix = OWNER_PREFIX
        recipient = owner_alert_email()
    else:
        raise ValueError(f"Unsupported alert type: {alert_type}")

    dedupe_key = f"{normalized_type}:{category}:{entity_type}:{entity_id}:{_today_key(now)}"
    existing = db.query(AlertRecord).filter(AlertRecord.dedupe_key == dedupe_key).first()
    if existing:
        suppressed = AlertRecord(
            alert_type=normalized_type,
            category=category,
            entity_type=entity_type,
            entity_id=entity_id,
            dedupe_key=f"{dedupe_key}:suppressed:{datetime.now().timestamp()}",
            subject=existing.subject,
            recipient=recipient,
            status="suppressed",
            details_json=_json({"reason": "duplicate_alert_same_day", **details}),
        )
        db.add(suppressed)
        db.flush()
        _audit(db, "ALERT_SUPPRESSED", suppressed, {"reason": "duplicate_alert_same_day"})
        db.commit()
        return suppressed

    subject = _subject(prefix, category, entity_label)
    alert = AlertRecord(
        alert_type=normalized_type,
        category=category,
        entity_type=entity_type,
        entity_id=entity_id,
        dedupe_key=dedupe_key,
        subject=subject,
        recipient=recipient,
        status="pending",
        details_json=_json(details),
    )
    db.add(alert)
    db.flush()
    _audit(db, "ALERT_GENERATED", alert, {"details": details})

    sent = send_email(recipient, subject, _html_body(prefix, category, entity_label, details))
    alert.status = "sent" if sent else "failed"
    if not sent:
        alert.last_error = "email_send_failed"
    _audit(db, "ALERT_SENT" if sent else "ALERT_FAILED", alert, {})
    db.commit()
    return alert


def developer_login_failure_alert(db: Session, employee_id: str, details: Optional[Dict[str, Any]] = None) -> AlertRecord:
    return generate_alert(
        db,
        alert_type="DEVELOPER",
        category="login_failures",
        entity_type="LOGIN",
        entity_id=employee_id,
        entity_label=employee_id,
        details=details or {},
    )


def developer_system_failure_alert(db: Session, component: str, details: Optional[Dict[str, Any]] = None) -> AlertRecord:
    return generate_alert(
        db,
        alert_type="DEVELOPER",
        category="system_failures",
        entity_type="SYSTEM",
        entity_id=component,
        entity_label=component,
        details=details or {},
    )


def developer_tamper_alert(db: Session, entity_id: str, details: Optional[Dict[str, Any]] = None) -> AlertRecord:
    return generate_alert(
        db,
        alert_type="DEVELOPER",
        category="tamper_alerts",
        entity_type="TAMPER",
        entity_id=entity_id,
        entity_label=entity_id,
        details=details or {},
    )


def owner_accountant_overdue_alerts(db: Session, now: Optional[datetime] = None):
    now = now or datetime.now()
    cutoff = now - timedelta(hours=48)
    bills = (
        db.query(Bill)
        .filter(
            Bill.is_test_data == False,
            Bill.review_required == 1,
            Bill.created_at <= cutoff,
        )
        .all()
    )
    return [
        generate_alert(
            db,
            alert_type="OWNER",
            category="accountant_overdue_48h",
            entity_type="BILL",
            entity_id=str(bill.id),
            entity_label=bill.bill_number,
            details={
                "bill_number": bill.bill_number,
                "customer_name": bill.customer_name,
                "created_at": bill.created_at,
                "review_required": bill.review_required,
            },
            now=now,
        )
        for bill in bills
    ]


def owner_uncleared_payment_alerts(db: Session, now: Optional[datetime] = None):
    now = now or datetime.now()
    cutoff = now - timedelta(days=7)
    payments = (
        db.query(Payment)
        .filter(
            Payment.created_at <= cutoff,
            Payment.status != "Green",
        )
        .all()
    )
    return [
        generate_alert(
            db,
            alert_type="OWNER",
            category="uncleared_payment_7d",
            entity_type="PAYMENT",
            entity_id=str(payment.id),
            entity_label=f"payment-{payment.id}",
            details={
                "payment_id": payment.id,
                "bill_id": payment.bill_id,
                "amount": float(payment.amount or 0),
                "mode": payment.mode,
                "status": payment.status,
                "created_at": payment.created_at,
            },
            now=now,
        )
        for payment in payments
    ]


def scan_login_failure_alerts(db: Session, now: Optional[datetime] = None):
    _ensure_alert_table(db)
    failures = db.query(LoginLog).filter(LoginLog.event_type.in_(["PASSWORD_FAILED", "LOGIN_FAILED"])).all()
    return [
        generate_alert(
            db,
            alert_type="DEVELOPER",
            category="login_failures",
            entity_type="LOGIN",
            entity_id=log.employee_id,
            entity_label=log.employee_id,
            details={"event_type": log.event_type, "ip_address": log.ip_address, "created_at": log.created_at},
            now=now,
        )
        for log in failures
    ]
