from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, Text, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import synonym
from backend.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String, unique=True, nullable=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False) # ADMIN, OWNER, ACCOUNTANT, STAFF, VIEWER
    email = Column(String, nullable=True)
    security_email = Column(String, nullable=True) # Private destination for OTP/Alerts
    hashed_password = Column(String, nullable=True)
    password_reset_required = Column(Boolean, default=False)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())

class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    value = Column(String)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class LoginLog(Base):
    __tablename__ = "login_logs"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String, nullable=False)
    event_type = Column(String, nullable=False) # LOGIN, LOGOUT, FAILED, TIMEOUT
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class OTP(Base):
    __tablename__ = "otps"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String, nullable=False)
    otp_code = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0)
    is_verified = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String, unique=True, nullable=False)
    employee_id = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    last_activity_at = Column(DateTime, server_default=func.now())
    created_at = Column(DateTime, server_default=func.now())

class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, index=True)
    bill_series = Column(String, nullable=True)
    bill_number = Column(String, unique=True, nullable=False)
    invoice_date = Column(DateTime, nullable=True)
    order_date = Column(DateTime, nullable=True)
    customer_name = Column(String, nullable=True)
    customer_mobile = Column(String, nullable=True)
    customer_address = Column(Text, nullable=True)
    
    taxable_value = Column(Numeric(12, 2), nullable=True)
    cgst = Column(Numeric(12, 2), nullable=True)
    sgst = Column(Numeric(12, 2), nullable=True)
    round_off = Column(Numeric(12, 2), nullable=True)
    amount = Column(Numeric(12, 2), nullable=False) # Rename back to amount for compatibility
    total_amount = synonym("amount")
    customer_purchase_amount = Column(Numeric(12, 2), default=0.0) # For Old Gold/Purchase
    advance_amount = Column(Numeric(12, 2), default=0.0) # For Advance adjusted
    advance_source = Column(String, nullable=True) # CASH, UPI, NEFT, RTGS, CARD, CHEQUE, MIXED, UNKNOWN
    advance_verification_status = Column(String, default="UNVERIFIED") # UNVERIFIED, VERIFIED, REJECTED
    
    payment_mode = Column(String, nullable=True)
    bank_name = Column(String, nullable=True)
    reference_no = Column(String, nullable=True)
    
    status = Column(String, default="Yellow")
    status_text = Column(String, nullable=True)
    review_required = Column(Integer, default=1)
    is_test_data = Column(Boolean, default=False)
    is_delivered = Column(Boolean, default=False)
    delivered_at = Column(DateTime, nullable=True)
    delivery_approved_by = Column(String, nullable=True)
    
    reversal_date = Column(DateTime, nullable=True)
    reversal_reason = Column(String, nullable=True)
    
    pdf_path = Column(String, nullable=True)
    pdf_hash = Column(String, nullable=True)
    raw_extracted_text = Column(Text, nullable=True)
    
    parsed_items_json = Column(Text, nullable=True) # To store JSON string of item details
    amount_in_words = Column(String, nullable=True) # To cross-reference with Total Amount
    
    cash_received = Column(Numeric(12, 2), default=0.0)
    bank_received = Column(Numeric(12, 2), default=0.0)
    card_received = Column(Numeric(12, 2), default=0.0)
    sms_confirmed_amount = Column(Numeric(12, 2), default=0.0)
    email_confirmed_amount = Column(Numeric(12, 2), default=0.0)
    remaining_amount = Column(Numeric(12, 2), default=0.0)
    
    invoice_generated_at = Column(DateTime, nullable=True)
    ingested_at = Column(DateTime, server_default=func.now())
    created_at = Column(DateTime, server_default=func.now())

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    mode = Column(String, nullable=False)
    bank_name = Column(String, nullable=True)
    utr_reference = Column(String, nullable=True)
    cheque_number = Column(String, nullable=True)
    payment_date = Column(DateTime, nullable=True)
    status = Column(String, default="Yellow")
    created_at = Column(DateTime, server_default=func.now())

class BankAlert(Base):
    __tablename__ = "bank_alerts"

    id = Column(Integer, primary_key=True, index=True)
    bank_name = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    utr_reference = Column(String, unique=True, index=True, nullable=True)
    sender = Column(String, nullable=False)
    received_at = Column(DateTime, nullable=False)
    raw_text = Column(Text, nullable=False)
    reconciled = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

class SMSAlert(Base):
    __tablename__ = "sms_alerts"

    id = Column(Integer, primary_key=True, index=True)
    sms_id = Column(String, unique=True, nullable=True)
    sender = Column(String, nullable=False)
    transaction_timestamp = Column(DateTime, nullable=False)
    bank_name = Column(String, nullable=True)
    account_suffix = Column(String, nullable=True)
    credit_or_debit = Column(String, nullable=True) # CREDIT, DEBIT
    amount = Column(Numeric(12, 2), nullable=False)
    utr_reference = Column(String, nullable=True)
    payer_name = Column(String, nullable=True)
    raw_body = Column(Text, nullable=False)
    email_message_id = Column(String, nullable=True)
    parsed_confidence = Column(Numeric(5, 2), default=0.0)
    created_at = Column(DateTime, server_default=func.now())

class Cheque(Base):
    __tablename__ = "cheques"

    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False)
    cheque_number = Column(String, nullable=False)
    bank_name = Column(String, nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)
    customer_name = Column(String, nullable=True)
    cheque_date = Column(DateTime, nullable=True)
    deposit_date = Column(DateTime, nullable=True)
    expected_clearance_date = Column(DateTime, nullable=True)
    status = Column(String, default="Blue")
    cleared_at = Column(DateTime, nullable=True)
    return_reason = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class MaintenanceSession(Base):
    __tablename__ = "maintenance_sessions"

    id = Column(Integer, primary_key=True, index=True)
    developer_id = Column(String, nullable=False)
    start_at = Column(DateTime, server_default=func.now())
    end_at = Column(DateTime, nullable=True)
    reason = Column(String, nullable=False)
    actions_performed = Column(Text, nullable=True)
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

class AlertRecord(Base):
    __tablename__ = "alert_records"

    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String, nullable=False) # DEVELOPER, OWNER
    category = Column(String, nullable=False)
    entity_type = Column(String, nullable=True)
    entity_id = Column(String, nullable=True)
    dedupe_key = Column(String, unique=True, index=True, nullable=False)
    subject = Column(String, nullable=False)
    recipient = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending") # pending, sent, failed, suppressed
    details_json = Column(Text, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class BankDocument(Base):
    __tablename__ = "bank_documents"

    id = Column(Integer, primary_key=True, index=True)
    bank_name = Column(String, nullable=True)
    classification = Column(String, default="UNKNOWN_BANK_DOCUMENT")
    classification_reason = Column(String, nullable=True)
    file_type = Column(String, nullable=True) # PDF, XLS, XLSX, UNKNOWN
    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size_bytes = Column(Integer, default=0)
    file_hash = Column(String, unique=True, index=True, nullable=False)
    source_email_id = Column(String, nullable=True)
    sender = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    received_at = Column(DateTime, nullable=True)
    status = Column(String, default="SAVED") # SAVED, TEXT_EXTRACTED, PARSED, NEEDS_PASSWORD, UNSUPPORTED_FORMAT, DUPLICATE, FAILED
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class BankDocumentTransaction(Base):
    __tablename__ = "bank_document_transactions"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("bank_documents.id"), nullable=False)
    
    # Extracted Data (Nullable for raw text lines)
    transaction_date = Column(DateTime, nullable=True)
    description = Column(Text, nullable=True)
    amount = Column(Numeric(12, 2), nullable=True)
    dr_cr = Column(String, nullable=True) # "CREDIT", "DEBIT"
    balance = Column(Numeric(12, 2), nullable=True)
    reference_number = Column(String, nullable=True)
    
    # Auditing / Metadata
    line_number = Column(Integer, nullable=True)
    raw_text = Column(Text, nullable=True) # The raw extracted line or row JSON
    
    status = Column(String, default="EXTRACTED") # EXTRACTED, ERROR
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, server_default=func.now())
