import random
import string
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from backend.models import User, OTP, Session as SessionModel, LoginLog
from backend.email_notifier import send_otp_email

logger = logging.getLogger("AuthService")

OTP_EXPIRY_MINUTES = 5
MAX_LOGIN_ATTEMPTS = 5
SESSION_TIMEOUT_HOURS = 8

def generate_otp(length: int = 6) -> str:
    return ''.join(random.choices(string.digits, k=length))

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password: return False
    return hash_password(plain_password) == hashed_password

def create_otp(db: Session, employee_id: str, is_resend: bool = False) -> Optional[str]:
    user = db.query(User).filter(User.employee_id == employee_id).first()
    if not user:
        logger.error(f"User {employee_id} not found.")
        return None

    # Priority: security_email, then primary email
    target_email = user.security_email if user.security_email else user.email
    if not target_email:
        logger.error(f"User {employee_id} has no registered email.")
        return None

    # Mandate: Invalidate previous unused OTPs for same employee_id
    db.query(OTP).filter(OTP.employee_id == employee_id).delete()

    otp_code = generate_otp()
    expires_at = datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    
    new_otp = OTP(
        employee_id=employee_id,
        otp_code=otp_code,
        expires_at=expires_at,
        attempts=0
    )
    db.add(new_otp)
    db.commit()
    
    # Send actual email
    sent = send_otp_email(target_email, otp_code)
    if not sent:
        logger.warning(f"Failed to send OTP email to {target_email}")
    
    event_type = "OTP_RESENT" if is_resend else "OTP_SENT"
    log_event(db, employee_id, event_type)
    
    logger.info(f"{event_type} to {target_email}. Expires at {expires_at}")
    return otp_code

def verify_otp(db: Session, employee_id: str, otp_code: str) -> bool:
    otp_code = otp_code.strip()
    
    # Find the latest unused OTP record
    otp_record = db.query(OTP).filter(
        OTP.employee_id == employee_id,
        OTP.is_verified == 0
    ).order_by(OTP.created_at.desc()).first()
    
    if not otp_record:
        logger.warning(f"OTP_VERIFY_FAILED: No active OTP found for {employee_id}")
        log_event(db, employee_id, "OTP_NOT_FOUND")
        return False

    # Check Expiry
    if otp_record.expires_at < datetime.now():
        logger.warning(f"OTP_EXPIRED for {employee_id} at {otp_record.expires_at}")
        log_event(db, employee_id, "OTP_EXPIRED")
        db.delete(otp_record)
        db.commit()
        return False

    # Check Max Attempts
    if otp_record.attempts >= MAX_LOGIN_ATTEMPTS:
        logger.warning(f"OTP_LOCKED: Too many attempts for {employee_id}")
        log_event(db, employee_id, "OTP_LOCKED")
        return False

    # Check Code Match
    if otp_record.otp_code == otp_code:
        # Success!
        otp_record.is_verified = 1
        # Consumed - we can either update or delete. User says "single use". 
        # I'll delete to be safe or mark verified. Let's delete.
        db.delete(otp_record)
        db.commit()
        log_event(db, employee_id, "OTP_VERIFY_SUCCESS")
        return True
    else:
        # Failure - increment attempts
        otp_record.attempts += 1
        db.commit()
        logger.warning(f"OTP_VERIFY_FAILED: Code mismatch for {employee_id} (Attempt {otp_record.attempts})")
        log_event(db, employee_id, "OTP_VERIFY_FAILED")
        return False

def create_user_session(db: Session, employee_id: str) -> str:
    session_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    expires_at = datetime.now() + timedelta(hours=SESSION_TIMEOUT_HOURS)
    
    new_session = SessionModel(
        employee_id=employee_id,
        session_token=session_token,
        expires_at=expires_at
    )
    db.add(new_session)
    db.commit()
    return session_token

def validate_session(db: Session, token: str) -> Optional[str]:
    session = db.query(SessionModel).filter(
        SessionModel.session_token == token,
        SessionModel.expires_at > datetime.now()
    ).first()
    
    if session:
        return session.employee_id
    return None

def log_event(db: Session, employee_id: str, event: str, ip: str = None):
    log = LoginLog(
        employee_id=employee_id,
        event_type=event,
        ip_address=ip
    )
    db.add(log)
    db.commit()
