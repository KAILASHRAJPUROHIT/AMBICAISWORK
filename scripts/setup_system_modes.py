from backend.database import SessionLocal
from backend.models import SystemSetting

def setup_system_modes():
    db = SessionLocal()
    try:
        # 1. System Mode
        mode = db.query(SystemSetting).filter(SystemSetting.key == "system_mode").first()
        if not mode:
            print("Initializing system_mode to PRODUCTION")
            mode = SystemSetting(key="system_mode", value="PRODUCTION")
            db.add(mode)
        
        # 2. Maintenance Reason
        reason = db.query(SystemSetting).filter(SystemSetting.key == "maintenance_reason").first()
        if not reason:
            reason = SystemSetting(key="maintenance_reason", value="None")
            db.add(reason)
            
        db.commit()
        print("Success.")
    finally:
        db.close()

if __name__ == "__main__":
    setup_system_modes()
