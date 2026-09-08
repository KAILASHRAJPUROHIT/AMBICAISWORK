import re

auth_service_path = "backend/auth_service.py"
with open(auth_service_path, "r", encoding="utf-8") as f:
    auth_service = f.read()

# Add imports
imports_to_add = """import pyotp
import qrcode
import base64
import io
from backend.models import User, OTP, Session as SessionModel, LoginLog, SystemSetting
from backend.security import encrypt_secret, decrypt_secret
"""
auth_service = auth_service.replace(
    "from backend.models import User, OTP, Session as SessionModel, LoginLog",
    imports_to_add
)

# Add TOTP functions
totp_funcs = """
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

"""
if "def get_totp_secret" not in auth_service:
    auth_service += totp_funcs

with open(auth_service_path, "w", encoding="utf-8") as f:
    f.write(auth_service)
    
review_api_path = "backend/review_api.py"
with open(review_api_path, "r", encoding="utf-8") as f:
    review_api = f.read()

# Update login
login_old = """    # Get/Create OTP with cooldown
    otp_res = create_otp(db, user.employee_id)
    if otp_res.get("status") == "error":
        raise HTTPException(status_code=500, detail=otp_res["message"])
    
    # Email hint for masking
    email = user.security_email if user.security_email else user.email
    user_part, domain_part = email.split('@')
    masked_email = f"{user_part[0]}***{user_part[-1]}@{domain_part}"
    
    return {
        "status": otp_res["status"],
        "otp_sent": otp_res["otp_sent"],
        "message": otp_res["message"],
        "resend_available_in": otp_res["resend_available_in"],
        "expires_in": otp_res["expires_in"],
        "masked_email": masked_email
    }"""
    
login_new = """    from backend.auth_service import get_totp_secret
    # Check if TOTP is enrolled
    if get_totp_secret(db, user.employee_id):
        return {
            "status": "totp_verify",
            "message": "Enter authenticator code"
        }
        
    # Get/Create OTP with cooldown (Legacy email bridge)
    otp_res = create_otp(db, user.employee_id)
    if otp_res.get("status") == "error":
        raise HTTPException(status_code=500, detail=otp_res["message"])
    
    # Email hint for masking
    email = user.security_email if user.security_email else user.email
    if email and '@' in email:
        user_part, domain_part = email.split('@')
        masked_email = f"{user_part[0]}***{user_part[-1]}@{domain_part}"
    else:
        masked_email = "your email"
    
    return {
        "status": "email_otp",
        "otp_sent": otp_res.get("otp_sent", True),
        "message": otp_res.get("message", ""),
        "resend_available_in": otp_res.get("resend_available_in", 60),
        "expires_in": otp_res.get("expires_in", 300),
        "masked_email": masked_email
    }"""

review_api = review_api.replace(login_old, login_new)

verify_old = """    # Verify OTP
    if verify_otp(db, target_id, request.otp_code):
        token = create_user_session(db, target_id)
        
        log_event(db, target_id, "LOGIN_SUCCESS", ip=req.client.host if req else None)
        return {
            "status": "success",
            "token": token,
            "user": {
                "name": user.name,
                "role": user.role,
                "employee_id": user.employee_id,
                "reset_required": user.password_reset_required == 1
            }
        }
    
    log_event(db, target_id, "LOGIN_FAILED", ip=req.client.host if req else None)
    raise HTTPException(status_code=401, detail="Invalid or expired OTP")"""

verify_new = """    from backend.auth_service import get_totp_secret, verify_totp_code, generate_totp_setup, set_pending_totp_secret
    totp_secret = get_totp_secret(db, target_id)
    
    if totp_secret:
        # Enrolled: Verify TOTP code
        if verify_totp_code(totp_secret, request.otp_code):
            token = create_user_session(db, target_id)
            log_event(db, target_id, "LOGIN_SUCCESS", ip=req.client.host if req else None)
            return {
                "status": "success",
                "token": token,
                "user": {
                    "name": user.name,
                    "role": user.role,
                    "employee_id": user.employee_id,
                    "reset_required": user.password_reset_required == 1
                }
            }
        log_event(db, target_id, "LOGIN_FAILED", ip=req.client.host if req else None)
        raise HTTPException(status_code=401, detail="Invalid Authenticator code")
    else:
        # Not enrolled: Verify Email OTP, then generate TOTP setup
        if verify_otp(db, target_id, request.otp_code):
            setup_data = generate_totp_setup(target_id)
            set_pending_totp_secret(db, target_id, setup_data["secret"])
            return {
                "status": "totp_setup",
                "secret": setup_data["secret"],
                "qr_b64": setup_data["qr_b64"]
            }
        
        log_event(db, target_id, "LOGIN_FAILED", ip=req.client.host if req else None)
        raise HTTPException(status_code=401, detail="Invalid or expired Email OTP")"""
review_api = review_api.replace(verify_old, verify_new)

resend_old = """    # Generate new OTP (create_otp handles invalidation of old ones)"""
resend_new = """    from backend.auth_service import get_totp_secret
    if get_totp_secret(db, user.employee_id):
        raise HTTPException(status_code=400, detail="Resend disabled for TOTP users")
        
    # Generate new OTP (create_otp handles invalidation of old ones)"""
review_api = review_api.replace(resend_old, resend_new)

totp_enroll = """
@app.post("/api/auth/totp-enroll")
async def totp_enroll(request: VerifyRequest, db: Session = Depends(get_db), req: Request = None):
    from backend.auth_service import get_pending_totp_secret, verify_totp_code, set_totp_secret, create_user_session, log_event
    user = db.query(User).filter(func.lower(User.employee_id) == request.employee_id.lower()).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user")
    target_id = user.employee_id
    
    pending_secret = get_pending_totp_secret(db, target_id)
    if not pending_secret:
        raise HTTPException(status_code=400, detail="No pending TOTP setup found")
        
    if verify_totp_code(pending_secret, request.otp_code):
        set_totp_secret(db, target_id, pending_secret)
        token = create_user_session(db, target_id)
        log_event(db, target_id, "LOGIN_SUCCESS", ip=req.client.host if req else None)
        return {
            "status": "success",
            "token": token,
            "user": {
                "name": user.name,
                "role": user.role,
                "employee_id": user.employee_id,
                "reset_required": user.password_reset_required == 1
            }
        }
    
    raise HTTPException(status_code=401, detail="Invalid Authenticator code")
"""
if "@app.post(\"/api/auth/totp-enroll\")" not in review_api:
    review_api += totp_enroll

with open(review_api_path, "w", encoding="utf-8") as f:
    f.write(review_api)

print("Backend updated.")
