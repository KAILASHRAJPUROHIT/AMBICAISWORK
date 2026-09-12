# Ported from payment-auditor/backend/models.py — only the tables the
# bank-activity notifier actually needs (SMSAlert, SystemSetting, AuditLog).
# None of these have foreign keys into Bill/Payment/Cheque, so they lift out
# clean with no schema changes.
from sqlalchemy import Column, Integer, String, Numeric, Text, DateTime, func
from database import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    value = Column(String)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SMSAlert(Base):
    __tablename__ = "sms_alerts"

    id = Column(Integer, primary_key=True, index=True)
    sms_id = Column(String, unique=True, nullable=True)
    sender = Column(String, nullable=False)
    transaction_timestamp = Column(DateTime, nullable=False)
    bank_name = Column(String, nullable=True)
    account_suffix = Column(String, nullable=True)
    credit_or_debit = Column(String, nullable=True)  # CREDIT, DEBIT
    amount = Column(Numeric(12, 2), nullable=False)
    utr_reference = Column(String, nullable=True)
    payer_name = Column(String, nullable=True)
    raw_body = Column(Text, nullable=False)
    email_message_id = Column(String, nullable=True)
    parsed_confidence = Column(Numeric(5, 2), default=0.0)
    created_at = Column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(Integer, nullable=False)
    action = Column(String, nullable=False)
    old_status = Column(String, nullable=True)
    new_status = Column(String, nullable=True)
    actor = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    metadata_json = Column(Text, nullable=True)
