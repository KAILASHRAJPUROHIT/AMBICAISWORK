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
    return hash_password(plain_password) == hashed_password

def create_otp(db: Session, employee_id: str) -> Optional[str]:
    user = db.query(User).filter(User.employee_id == employee_id).first()
    if not user or not user.email:
        logger.error(f"User {employee_id} not found or has no email.")
        return None

    # Clear old OTPs
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
    sent = send_otp_email(user.email, otp_code)
    if not sent:
        logger.warning(f"Failed to send OTP email to {user.email}")
        
    logger.info(f"OTP created and sent to {user.email}. Expires at {expires_at}")
    return otp_code

def verify_otp(db: Session, employee_id: str, otp_code: str) -> bool:
    otp_record = db.query(OTP).filter(
        OTP.employee_id == employee_id,
        OTP.otp_code == otp_code,
        OTP.expires_at > datetime.now()
    ).first()
    
    if otp_record:
        if otp_record.attempts >= MAX_LOGIN_ATTEMPTS:
            logger.warning(f"Too many OTP attempts for {employee_id}")
            return False
            
        # OTP is single use, delete it after success
        db.delete(otp_record)
        db.commit()
        return True
    
    # Increment attempts on failure
    otp_record = db.query(OTP).filter(OTP.employee_id == employee_id).first()
    if otp_record:
        otp_record.attempts += 1
        db.commit()
        
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
        # Sliding window? For now just return
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
