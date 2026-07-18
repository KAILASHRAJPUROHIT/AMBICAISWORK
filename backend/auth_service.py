import random
import string
import logging
import hashlib
import hmac
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.models import User, OTP, Session as SessionModel, LoginLog
from backend.email_notifier import send_otp_email
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger("AuthService")

OTP_EXPIRY_MINUTES = 5
MAX_LOGIN_ATTEMPTS = 5
SESSION_TIMEOUT_HOURS = 8
RESEND_COOLDOWN_SECONDS = 60

def generate_otp(length: int = 6) -> str:
    return ''.join(random.choices(string.digits, k=length))

def hash_password(password: str) -> str:
    """Return a salted, deliberately expensive password hash."""
    return generate_password_hash(password, method="scrypt")


def validate_password_strength(password: str) -> str | None:
    """Return a user-facing validation error, or None for an acceptable password."""
    if len(password) < 12:
        return "Password must be at least 12 characters"
    if not re.search(r"[a-z]", password) or not re.search(r"[A-Z]", password):
        return "Password must include upper- and lower-case letters"
    if not re.search(r"\d", password):
        return "Password must include a number"
    return None


def is_legacy_password_hash(hashed_password: str | None) -> bool:
    """Identify the original unsalted SHA-256 format for login migration."""
    return bool(hashed_password and re.fullmatch(r"[0-9a-fA-F]{64}", hashed_password))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    if is_legacy_password_hash(hashed_password):
        legacy = hashlib.sha256(plain_password.encode()).hexdigest()
        return hmac.compare_digest(legacy, hashed_password.lower())
    try:
        return check_password_hash(hashed_password, plain_password)
    except (ValueError, TypeError):
        return False

def create_otp(db: Session, employee_id: str, is_resend: bool = False, business_name: str = "Payment Auditor") -> Dict[str, Any]:
    """
    Creates or returns existing OTP with cooldown logic.
    Rules:
    - If unused OTP < 60s exists: return cooldown.
    - If unused OTP > 60s exists: invalidate and send new.

    business_name: the tenant's own business name, resolved by the caller
    (see review_api.py) from its business profile — passed through to
    send_otp_email so each business's OTP mail is branded correctly rather
    than a single hardcoded name across every tenant.
    """
    user = db.query(User).filter(User.employee_id == employee_id).first()
    if not user:
        return {"status": "error", "message": "User not found"}

    target_email = user.security_email if user.security_email else user.email
    if not target_email:
        return {"status": "error", "message": "No registered email"}

    # Check for existing active OTP
    existing_otp = db.query(OTP).filter(
        OTP.employee_id == employee_id,
        OTP.is_verified == 0,
        OTP.expires_at > datetime.now()
    ).order_by(OTP.created_at.desc()).first()

    if existing_otp:
        age_seconds = (datetime.now() - existing_otp.created_at).total_seconds()
        if age_seconds < RESEND_COOLDOWN_SECONDS:
            logger.info(f"OTP_SEND_SKIPPED_COOLDOWN for {employee_id} (Age: {int(age_seconds)}s)")
            return {
                "status": "cooldown",
                "otp_sent": False,
                "resend_available_in": int(RESEND_COOLDOWN_SECONDS - age_seconds),
                "expires_in": int((existing_otp.expires_at - datetime.now()).total_seconds()),
                "message": "OTP already sent. Please wait before requesting another."
            }
        else:
            # Invalidate old one
            db.delete(existing_otp)
            db.commit()

    # Generate fresh OTP
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
    sent = send_otp_email(target_email, otp_code, business_name=business_name)
    
    event_type = "OTP_RESENT" if is_resend else "OTP_SENT"
    if sent:
        log_event(db, employee_id, event_type)
        logger.info(f"{event_type} to {target_email}. Expires at {expires_at}")
    else:
        logger.error(f"OTP_EMAIL_SEND_FAILED to {target_email}")
        
    return {
        "status": "success",
        "otp_sent": sent,
        "resend_available_in": RESEND_COOLDOWN_SECONDS,
        "expires_in": OTP_EXPIRY_MINUTES * 60,
        "message": "OTP sent to your registered email" if sent else "Failed to send email. Please try again."
    }

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
        otp_record.is_verified = 1
        db.delete(otp_record)
        db.commit()
        log_event(db, employee_id, "OTP_VERIFY_SUCCESS")
        return True
    else:
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
