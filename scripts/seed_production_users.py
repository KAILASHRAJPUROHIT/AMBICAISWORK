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
    # Ensure table exists
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # 1. OWNER
        owner_email = "info@aradhanajewellers.com"
        owner = db.query(User).filter(User.email == owner_email).first()
        if not owner:
            print(f"Creating OWNER: {owner_email}")
            owner = User(
                employee_id="OWNER-01",
                name="Aradhana Owner",
                email=owner_email,
                role="OWNER",
                hashed_password=hash_password("Owner@123"), # Default password
                is_active=1
            )
            db.add(owner)
        else:
            print(f"OWNER already exists.")
            owner.role = "OWNER"
            owner.hashed_password = hash_password("Owner@123")

        # 2. ACCOUNTANT
        acc_email = "shreearadhana1001@gmail.com"
        accountant = db.query(User).filter(User.email == acc_email).first()
        if not accountant:
            print(f"Creating ACCOUNTANT: {acc_email}")
            accountant = User(
                employee_id="ACC-01",
                name="Aradhana Accountant",
                email=acc_email,
                role="ACCOUNTANT",
                hashed_password=hash_password("Acc@123"), # Default password
                is_active=1
            )
            db.add(accountant)
        else:
            print(f"ACCOUNTANT already exists.")
            accountant.role = "ACCOUNTANT"
            accountant.hashed_password = hash_password("Acc@123")

        db.commit()
        print("Seeding complete.")
    finally:
        db.close()

if __name__ == "__main__":
    seed_users()
