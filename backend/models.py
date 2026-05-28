from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, Text
from sqlalchemy.sql import func
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, index=True)
    bill_number = Column(String, unique=True, nullable=False)
    customer_name = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    status = Column(String, default="Yellow")
    created_at = Column(DateTime, server_default=func.now())

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    mode = Column(String, nullable=False)
    utr_reference = Column(String, nullable=True)
    status = Column(String, default="Yellow")
    created_at = Column(DateTime, server_default=func.now())

class BankAlert(Base):
    __tablename__ = "bank_alerts"

    id = Column(Integer, primary_key=True, index=True)
    bank_name = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    utr_reference = Column(String, nullable=True)
    sender = Column(String, nullable=False)
    received_at = Column(DateTime, nullable=False)
    raw_text = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class SMSAlert(Base):
    __tablename__ = "sms_alerts"

    id = Column(Integer, primary_key=True, index=True)
    phone_source = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    utr_reference = Column(String, nullable=True)
    received_at = Column(DateTime, nullable=False)
    raw_text = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class Cheque(Base):
    __tablename__ = "cheques"

    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False)
    cheque_number = Column(String, nullable=False)
    bank_name = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    status = Column(String, default="Blue")
    deposited_at = Column(DateTime, nullable=True)
    cleared_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(Integer, nullable=False)
    action = Column(String, nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    performed_by = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
