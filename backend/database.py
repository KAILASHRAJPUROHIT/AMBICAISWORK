from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import sys

# Centralized path resolution for production environment
def get_base_dir():
    # Priority 1: If frozen (EXE)
    if getattr(sys, 'frozen', False):
        exe_path = os.path.abspath(sys.executable)
        exe_dir = os.path.dirname(exe_path)
        
        # Log for debugging during startup
        # Note: sys.stdout might be redirected in windowed mode
        
        # If the EXE is inside the 'dist' folder, the project root is one level up
        if os.path.basename(exe_dir).lower() == 'dist':
            root = os.path.dirname(exe_dir)
            if os.path.exists(os.path.join(root, "aradhana_dev.db")):
                return root
        
        # If we are already in the root (e.g. EXE moved to root)
        if os.path.exists(os.path.join(exe_dir, "aradhana_dev.db")):
            return exe_dir
            
        # Last resort: use the directory of the EXE
        return exe_dir
        
    # Priority 2: Running as a script (CLI)
    # This file is at project_root/backend/database.py
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = get_base_dir()
DB_PATH = os.path.abspath(os.path.join(BASE_DIR, "aradhana_dev.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# For diagnostic logging
print(f"DATABASE_PATH_USED={DB_PATH}")

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
