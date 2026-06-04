import os
import shutil
import logging
import threading
import time
from datetime import datetime, time as dtime
from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models import Bill, AuditLog
import json

logger = logging.getLogger("InvoiceLifecycle")
logging.basicConfig(level=logging.INFO)

WATCH_PATH = r"C:\Aradhana\InvoicePDFs"
ARCHIVE_ROOT = r"C:\Aradhana\OLD"
DUPLICATE_ROOT = r"C:\Aradhana\DUPLICATE"

# Ensure directories exist
for path in [WATCH_PATH, ARCHIVE_ROOT, DUPLICATE_ROOT]:
    os.makedirs(path, exist_ok=True)

def robust_copy(src, dest, retries=5, delay=2):
    """Attempt to copy a file, retrying if it is locked. Never deletes the source."""
    for i in range(retries):
        try:
            shutil.copy2(src, dest)
            return True
        except PermissionError as e:
            logger.warning(f"File locked, retrying copy {src} -> {dest} (Attempt {i+1}/{retries})")
            time.sleep(delay)
        except Exception as e:
            logger.error(f"Error copying {src} to {dest}: {e}")
            break
    return False

def handle_duplicate(file_path, db: Session, reason="Duplicate detected"):
    """Log duplicate detection. Do NOT move or delete source invoices."""
    filename = os.path.basename(file_path)
    logger.info(f"Ignored duplicate {filename} (Reason: {reason}) - Source kept intact per mandate.")
    
    # Log to audit logs
    log = AuditLog(
        entity_type="FILE",
        entity_id=0,
        action="DUPLICATE_DETECTED",
        old_status="ACTIVE",
        new_status="IGNORED",
        actor="SYSTEM_LIFECYCLE",
        metadata_json=json.dumps({
            "original_path": file_path,
            "reason": reason
        })
    )
    db.add(log)
    db.commit()

def get_store_opening_time():
    """Get today's store opening time based on the rules."""
    now = datetime.now()
    day_of_week = now.weekday() # 0=Mon, 3=Thu, 6=Sun
    
    if day_of_week == 3: # Thursday
        return dtime(12, 0)
    return dtime(10, 0)

def run_archive_job():
    """Job to move verified/closed invoices to the archive."""
    logger.info("Starting Daily Archive Job...")
    db = SessionLocal()
    try:
        # Rules: Move VERIFIED, CLOSED, ARCHIVED. Status in models is Case-Sensitive (Green, Red, etc.)
        # Based on existing logic: 
        # Green = Cleared
        # Blue = Cheque Pending Review / Partial
        # Yellow = Pending
        # Red = Error
        
        # Requirement says: VERIFIED, CLOSED, ARCHIVED. 
        # Let's map Green to VERIFIED/CLOSED for this purpose.
        
        bills_to_archive = db.query(Bill).filter(
            Bill.status == "Green",
            Bill.pdf_path.isnot(None)
        ).all()
        
        archive_date_str = datetime.now().strftime("%Y-%m-%d")
        archive_dir = os.path.join(ARCHIVE_ROOT, archive_date_str)
        os.makedirs(archive_dir, exist_ok=True)
        
        archived_count = 0
        for bill in bills_to_archive:
            if not os.path.exists(bill.pdf_path):
                continue
            
            # Ensure it's not already in an archive path
            if ARCHIVE_ROOT.lower() in bill.pdf_path.lower():
                continue
                
            filename = os.path.basename(bill.pdf_path)
            dest_path = os.path.join(archive_dir, filename)
            
            if robust_copy(bill.pdf_path, dest_path):
                bill.pdf_path = dest_path
                archived_count += 1
                
                log = AuditLog(
                    entity_type="BILL",
                    entity_id=bill.id,
                    action="ARCHIVE",
                    old_status=bill.status,
                    new_status="ARCHIVED",
                    actor="SYSTEM_LIFECYCLE",
                    metadata_json=json.dumps({
                        "dest_path": dest_path
                    })
                )
                db.add(log)
            else:
                logger.error(f"Failed to archive bill {bill.bill_number} after retries")
                
        db.commit()
        logger.info(f"Archive job complete. Moved {archived_count} files.")
    finally:
        db.close()

def lifecycle_scheduler_loop():
    """Background thread to run archival at store opening."""
    last_run_date = None
    
    while True:
        now = datetime.now()
        opening_time = get_store_opening_time()
        
        # Run if it's past opening time and we haven't run today
        if now.time() >= opening_time and (last_run_date is None or last_run_date != now.date()):
            try:
                run_archive_job()
                last_run_date = now.date()
            except Exception as e:
                logger.error(f"Error in lifecycle scheduler: {e}")
        
        time.sleep(300) # Check every 5 minutes

def start_lifecycle_automation():
    thread = threading.Thread(target=lifecycle_scheduler_loop, daemon=True)
    thread.start()
    logger.info("Invoice Lifecycle Automation thread started.")
