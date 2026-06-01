import random
import string
import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from backend.models import User, OTP, Session as SessionModel, LoginLog
from backend.database import SessionLocal
from backend.rbac import UserRole

logger = logging.getLogger("Auth")

SESSION_TIMEOUT_MINUTES = 3
OTP_EXPIRY_MINUTES = 3

def generate_otp() -> str:
    return ''.join(random.choices(string.digits, k=6))

def create_otp(db: Session, employee_id: str) -> str:
    otp_code = generate_otp()
    expires_at = datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    
    new_otp = OTP(
        employee_id=employee_id,
        otp_code=otp_code,
        expires_at=expires_at
    )
    db.add(new_otp)
    db.commit()
    logger.info(f"OTP created for {employee_id}. Expires at {expires_at}")
    return otp_code

def verify_otp(db: Session, employee_id: str, code: str) -> bool:
    otp_record = db.query(OTP).filter(
        OTP.employee_id == employee_id,
        OTP.otp_code == code,
        OTP.expires_at > datetime.now(),
        OTP.is_verified == 0
    ).order_by(OTP.created_at.desc()).first()
    
    if otp_record:
        otp_record.is_verified = 1
        db.commit()
        return True
    return False

def create_user_session(db: Session, employee_id: str) -> str:
    token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    expires_at = datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    
    new_session = SessionModel(
        session_token=token,
        employee_id=employee_id,
        expires_at=expires_at,
        last_activity_at=datetime.now()
    )
    db.add(new_session)
    db.commit()
    return token

def validate_session(db: Session, token: str) -> Optional[str]:
    session = db.query(SessionModel).filter(
        SessionModel.session_token == token,
        SessionModel.expires_at > datetime.now()
    ).first()
    
    if session:
        # Check inactivity
        if datetime.now() > session.last_activity_at + timedelta(minutes=SESSION_TIMEOUT_MINUTES):
            logger.info(f"Session {token} timed out due to inactivity.")
            return None
            
        # Update activity
        session.last_activity_at = datetime.now()
        session.expires_at = datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
        db.commit()
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
