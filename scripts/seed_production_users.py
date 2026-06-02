from pathlib import Path
import sys
import os

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal, engine
from backend.models import User, Base
from sqlalchemy import text
import hashlib

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def seed_users():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # 1. OWNER
        owner_email = "info@aradhanajewellers.com"
        owner_security_email = "kuldeeprajpurohit309@gmail.com"
        
        owner = db.query(User).filter(User.employee_id == "OWNER-01").first()
        if not owner:
            print(f"Creating OWNER-01")
            owner = User(
                employee_id="OWNER-01",
                name="Aradhana Owner",
                email=owner_email,
                security_email=owner_security_email,
                role="OWNER",
                hashed_password=hash_password("Owner@123"),
                is_active=1
            )
            db.add(owner)
        else:
            owner.security_email = owner_security_email
            owner.role = "OWNER"

        # 2. ACCOUNTANT
        acc_email = "shreearadhana1001@gmail.com"
        accountant = db.query(User).filter(User.employee_id == "ACC-01").first()
        if not accountant:
            print(f"Creating ACC-01")
            accountant = User(
                employee_id="ACC-01",
                name="Aradhana Accountant",
                email=acc_email,
                role="ACCOUNTANT",
                hashed_password=hash_password("Acc@123"),
                is_active=1
            )
            db.add(accountant)
        else:
            accountant.role = "ACCOUNTANT"

        # 3. DEVELOPER (DEV-01)
        dev_id = "DEV-01"
        dev_email = "hypergamer1231@gmail.com"
        dev_security_email = "info@aradhanajewellers.com" # MANDATE: OTP goes here
        
        developer = db.query(User).filter(User.employee_id == dev_id).first()
        if not developer:
            print(f"Creating {dev_id}")
            developer = User(
                employee_id=dev_id,
                name="Aradhana Developer",
                email=dev_email,
                security_email=dev_security_email,
                role="DEVELOPER",
                hashed_password=hash_password("Dev@12345"),
                is_active=1,
                password_reset_required=True # Force reset on first login
            )
            db.add(developer)
        else:
            print(f"Updating {dev_id}")
            developer.email = dev_email
            developer.security_email = dev_security_email
            developer.role = "DEVELOPER"
            developer.hashed_password = hash_password("Dev@12345")
            developer.is_active = 1
            developer.password_reset_required = True

        db.commit()
        
        # Log developer activation
        from backend.reconciliation.logic import log_audit
        log_audit(db, "User", developer.id, "USER_ACTIVATED", None, "DEVELOPER", "Account DEV-01 activated for production testing")
        db.commit()
        
        print("Seeding complete.")
    finally:
        db.close()

if __name__ == "__main__":
    seed_users()
