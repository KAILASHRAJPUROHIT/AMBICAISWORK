import random
import string
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
import pyotp
import qrcode
import base64
import io
from backend.models import User, OTP, Session as SessionModel, LoginLog, SystemSetting
from backend.security import encrypt_secret, decrypt_secret

from backend.email_notifier import send_otp_email

logger = logging.getLogger("AuthService")

OTP_EXPIRY_MINUTES = 5
MAX_LOGIN_ATTEMPTS = 5
SESSION_TIMEOUT_HOURS = 8
RESEND_COOLDOWN_SECONDS = 60

def generate_otp(length: int = 6) -> str:
    return ''.join(random.choices(string.digits, k=length))

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password: return False
    return hash_password(plain_password) == hashed_password

def create_otp(db: Session, employee_id: str, is_resend: bool = False) -> Dict[str, Any]:
    """
    Creates or returns existing OTP with cooldown logic.
    Rules:
    - If unused OTP < 60s exists: return cooldown.
    - If unused OTP > 60s exists: invalidate and send new.
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
    sent = send_otp_email(target_email, otp_code)
    
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

def get_totp_secret(db: Session, employee_id: str) -> Optional[str]:
    setting = db.query(SystemSetting).filter(SystemSetting.key == f"totp_secret_{employee_id}").first()
    if setting and setting.value:
        return decrypt_secret(setting.value)
    return None

def set_totp_secret(db: Session, employee_id: str, secret: str):
    key = f"totp_secret_{employee_id}"
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    encrypted = encrypt_secret(secret)
    if setting:
        setting.value = encrypted
    else:
        setting = SystemSetting(key=key, value=encrypted)
        db.add(setting)
    db.commit()

def generate_totp_setup(employee_id: str) -> Dict[str, str]:
    secret = pyotp.random_base32()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=employee_id, issuer_name="Aradhana Auditor")
    
    qr = qrcode.QRCode(version=1, box_size=5, border=2)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    
    return {
        "secret": secret,
        "qr_b64": f"data:image/png;base64,{b64}"
    }

def get_pending_totp_secret(db: Session, employee_id: str) -> Optional[str]:
    setting = db.query(SystemSetting).filter(SystemSetting.key == f"pending_totp_secret_{employee_id}").first()
    if setting and setting.value:
        return decrypt_secret(setting.value)
    return None

def set_pending_totp_secret(db: Session, employee_id: str, secret: str):
    key = f"pending_totp_secret_{employee_id}"
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    encrypted = encrypt_secret(secret)
    if setting:
        setting.value = encrypted
    else:
        setting = SystemSetting(key=key, value=encrypted)
        db.add(setting)
    db.commit()

def verify_totp_code(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code)

