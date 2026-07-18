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

# Were hardcoded to C:\Aradhana\InvoicePDFs, \OLD, \DUPLICATE — one
# specific business's own fixed absolute paths, which also meant this
# module could fail at import time on any deployment without a C:\Aradhana
# directory writable by the process. Business-neutral local defaults now;
# each env var lets a deployment point at its own real location.
_LIFECYCLE_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "invoice_lifecycle_data")
WATCH_PATH = os.environ.get("INVOICE_LIFECYCLE_WATCH_PATH", os.path.join(_LIFECYCLE_BASE, "inbox"))
ARCHIVE_ROOT = os.environ.get("INVOICE_LIFECYCLE_ARCHIVE_ROOT", os.path.join(_LIFECYCLE_BASE, "archive"))
DUPLICATE_ROOT = os.environ.get("INVOICE_LIFECYCLE_DUPLICATE_ROOT", os.path.join(_LIFECYCLE_BASE, "duplicate"))

# Ensure directories exist
for path in [WATCH_PATH, ARCHIVE_ROOT, DUPLICATE_ROOT]:
    os.makedirs(path, exist_ok=True)

def handle_duplicate(file_path, db: Session, reason="Duplicate detected"):
    """Move a duplicate file to the DUPLICATE folder."""
    filename = os.path.basename(file_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_name = f"{timestamp}_{filename}"
    dest_path = os.path.join(DUPLICATE_ROOT, dest_name)
    
    try:
        shutil.move(file_path, dest_path)
        logger.info(f"Moved duplicate {filename} to {dest_path}")
        
        # Log to audit logs
        log = AuditLog(
            entity_type="FILE",
            entity_id=0,
            action="DUPLICATE_MOVE",
            old_status="ACTIVE",
            new_status="DUPLICATE",
            actor="SYSTEM_LIFECYCLE",
            metadata_json=json.dumps({
                "original_path": file_path,
                "dest_path": dest_path,
                "reason": reason
            })
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to move duplicate {file_path}: {e}")

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
            
            try:
                shutil.move(bill.pdf_path, dest_path)
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
            except Exception as e:
                logger.error(f"Failed to archive bill {bill.bill_number}: {e}")
                
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
