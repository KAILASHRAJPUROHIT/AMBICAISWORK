from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import sys

# Centralized path resolution for production environment
def get_base_dir():
    if getattr(sys, 'frozen', False):
        exe_path = os.path.abspath(sys.executable)
        exe_dir = os.path.dirname(exe_path)
        if os.path.basename(exe_dir).lower() == 'dist':
            return os.path.dirname(exe_dir)
        return r"C:\Users\kaila\aradhana-payment-auditor\aradhana-payment-auditor"
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = get_base_dir()
DB_PATH = os.path.abspath(os.path.join(BASE_DIR, "aradhana_dev.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# For diagnostic logging
print(f"DATABASE_PATH_USED={DB_PATH}")

# Do NOT silently create empty database in the wrong place
if not os.path.exists(DB_PATH):
    print(f"FATAL: Database missing at {DB_PATH}")
    # We don't exit immediately here to allow imports to succeed, but check_db_integrity will fail.

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def check_db_integrity():
    """Fail startup if configured database does not contain required tables."""
    if not os.path.exists(DB_PATH):
        return False, f"Database file missing at {DB_PATH}"
        
    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        required = ["bills", "bank_alerts", "sms_alerts", "users"]
        for table in required:
            if table not in existing_tables:
                return False, f"Required table '{table}' missing in {DB_PATH}"
        return True, None
    except Exception as e:
        return False, f"Database integrity check failed: {str(e)}"

