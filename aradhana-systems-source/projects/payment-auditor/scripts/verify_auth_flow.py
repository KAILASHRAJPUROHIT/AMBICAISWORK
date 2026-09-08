from pathlib import Path
import sys
import os

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal
from backend.models import User, OTP, Session as SessionModel
from backend.auth_service import create_otp, verify_otp, create_user_session, validate_session
from datetime import datetime

def test_auth_flow():
    db = SessionLocal()
    try:
        print("\n=== AUTHENTICATION FLOW VERIFICATION ===")
        
        # 1. Setup Test User
        employee_id = "TEST-AUTH-99"
        user = db.query(User).filter(User.employee_id == employee_id).first()
        if not user:
            print(f"Creating test user {employee_id}...")
            user = User(
                employee_id=employee_id,
                name="Test Auditor",
                email="bankalerts@aradhanajewellers.com", # Using our poller email for test
                role="admin"
            )
            db.add(user)
            db.commit()
        
        # 2. OTP Generation (Step 4 & 5)
        print("Step 4 & 5: Generating and 'Sending' OTP...")
        otp_code = create_otp(db, employee_id)
        assert otp_code is not None
        print(f" -> OTP Generated: {otp_code}")
        
        # 3. OTP Verification (Step 7)
        print("Step 7: Verifying OTP...")
        is_valid = verify_otp(db, employee_id, otp_code)
        assert is_valid is True
        print(" -> OTP Verified Successfully.")
        
        # 4. Session Creation (Step 8)
        print("Step 8: Creating Session...")
        token = create_user_session(db, employee_id)
        assert token is not None
        print(f" -> Session Created. Token: {token[:10]}...")
        
        # 5. Access Check (Step 9)
        print("Step 9: Validating Session Access...")
        validated_id = validate_session(db, token)
        assert validated_id == employee_id
        print(f" -> Session Validated for User: {validated_id}")
        
        print("\n[SUCCESS] ALL AUTHENTICATION STEPS VERIFIED.")
        
    finally:
        # Cleanup
        db.query(SessionModel).filter(SessionModel.employee_id == employee_id).delete()
        db.query(OTP).filter(OTP.employee_id == employee_id).delete()
        db.query(User).filter(User.employee_id == employee_id).delete()
        db.commit()
        db.close()

if __name__ == "__main__":
    test_auth_flow()
