from pathlib import Path
import sys
import os
import argparse
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

# Add the project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal
from backend.models import SystemSetting

def get_checkpoint(db: Session):
    setting = db.query(SystemSetting).filter(SystemSetting.key == "last_email_checkpoint").first()
    if setting:
        return setting.value
    return "NOT SET (Using default: Today 10 AM)"

def set_checkpoint(db: Session, ts_str: str):
    # Validate format
    try:
        datetime.fromisoformat(ts_str)
    except ValueError:
        print(f"Error: Invalid ISO format '{ts_str}'. Use YYYY-MM-DDTHH:MM:SS")
        return

    setting = db.query(SystemSetting).filter(SystemSetting.key == "last_email_checkpoint").first()
    if not setting:
        setting = SystemSetting(key="last_email_checkpoint", value=ts_str)
        db.add(setting)
    else:
        setting.value = ts_str
    db.commit()
    print(f"Checkpoint updated to: {ts_str}")

def main():
    parser = argparse.ArgumentParser(description="Manage Email Poller Checkpoint")
    parser.add_argument("--show", action="store_true", help="Show current checkpoint")
    parser.add_argument("--reset-today", action="store_true", help="Reset checkpoint to today 00:00:00")
    parser.add_argument("--reset-yesterday", action="store_true", help="Reset checkpoint to yesterday 00:00:00")
    parser.add_argument("--set", type=str, help="Set checkpoint to custom ISO timestamp (YYYY-MM-DDTHH:MM:SS)")
    
    args = parser.parse_args()
    db = SessionLocal()
    
    try:
        if args.show or (not args.reset_today and not args.reset_yesterday and not args.set):
            print(f"Current Checkpoint: {get_checkpoint(db)}")
        
        if args.reset_today:
            ts = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            set_checkpoint(db, ts)
        elif args.reset_yesterday:
            ts = (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            set_checkpoint(db, ts)
        elif args.set:
            set_checkpoint(db, args.set)
            
    finally:
        db.close()

if __name__ == "__main__":
    main()
