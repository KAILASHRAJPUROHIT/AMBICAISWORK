from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class Status(Enum):
    Green = "Green"
    Yellow = "Yellow"
    Orange = "Orange"
    Red = "Red"
    Blue = "Blue"
    Grey = "Grey"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)

class Bill(Base):
    __tablename__ = "bills"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Float)
    status = Column(Enum(Status), default=Status.Yellow)
    created_at = Column(DateTime, default=datetime.utcnow)

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id"))
    amount = Column(Float)
    status = Column(Enum(Status), default=Status.Yellow)
    created_at = Column(DateTime, default=datetime.utcnow)

class BankAlert(Base):
    __tablename__ = "bank_alerts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    message = Column(String)
    status = Column(Enum(Status), default=Status.Yellow)
    created_at = Column(DateTime, default=datetime.utcnow)

class SMSAlert(Base):
    __tablename__ = "sms_alerts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    message = Column(String)
    status = Column(Enum(Status), default=Status.Yellow)
    created_at = Column(DateTime, default=datetime.utcnow)

class Cheque(Base):
    __tablename__ = "cheques"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Float)
    status = Column(Enum(Status), default=Status.Yellow)
    created_at = Column(DateTime, default=datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String)
    details = Column(String)
    status = Column(Enum(Status), default=Status.Yellow)
    created_at = Column(DateTime, default=datetime.utcnow)
