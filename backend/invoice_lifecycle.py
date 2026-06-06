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
DUPLICATE_MOVE_FAILED_PERMISSION = "DUPLICATE_MOVE_FAILED_PERMISSION"
DUPLICATE_PERMISSION_MESSAGE = "Duplicate PDF detected but archive move failed due to Windows share permission."

# Ensure directories exist
for path in [WATCH_PATH, ARCHIVE_ROOT, DUPLICATE_ROOT]:
    os.makedirs(path, exist_ok=True)

def _today_key():
    return datetime.now().strftime("%Y-%m-%d")

def _is_access_denied(error: Exception) -> bool:
    winerror = getattr(error, "winerror", None)
    errno = getattr(error, "errno", None)
    message = str(error).lower()
    return winerror == 5 or errno == 13 or isinstance(error, PermissionError) or "access is denied" in message

def _duplicate_metadata(file_path, reason, file_hash=None, dest_path=None, error=None):
    metadata = {
        "original_path": file_path,
        "filename": os.path.basename(file_path),
        "reason": reason,
        "file_hash": file_hash,
        "duplicate_day": _today_key(),
        "operator_message": DUPLICATE_PERMISSION_MESSAGE if error else None,
    }
    if dest_path:
        metadata["dest_path"] = dest_path
    if error:
        metadata["error"] = str(error)
    return metadata

def _log_duplicate_event(db: Session, action: str, new_status: str, metadata: dict):
    log = AuditLog(
        entity_type="FILE",
        entity_id=0,
        action=action,
        old_status="ACTIVE",
        new_status=new_status,
        actor="SYSTEM_LIFECYCLE",
        metadata_json=json.dumps(metadata)
    )
    db.add(log)
    db.commit()
    return log

def _metadata_matches(metadata_json, file_path, file_hash=None):
    try:
        metadata = json.loads(metadata_json or "{}")
    except json.JSONDecodeError:
        return False
    same_file = metadata.get("original_path") == file_path
    same_hash = file_hash and metadata.get("file_hash") == file_hash
    return (same_file or same_hash) and metadata.get("duplicate_day") == _today_key()

def duplicate_permission_ignored_today(db: Session, file_path: str, file_hash=None) -> bool:
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.action == DUPLICATE_MOVE_FAILED_PERMISSION)
        .order_by(AuditLog.created_at.desc())
        .limit(100)
        .all()
    )
    return any(_metadata_matches(log.metadata_json, file_path, file_hash) for log in logs)

def get_duplicate_quarantine_summary(db: Session):
    logs = db.query(AuditLog).filter(
        AuditLog.action.in_(["DUPLICATE_MOVE", DUPLICATE_MOVE_FAILED_PERMISSION])
    ).all()
    return {
        "total_duplicates": len(logs),
        "failed_moves": sum(1 for log in logs if log.action == DUPLICATE_MOVE_FAILED_PERMISSION),
        "ignored_until_permission_fixed": sum(1 for log in logs if log.action == DUPLICATE_MOVE_FAILED_PERMISSION),
        "operator_message": DUPLICATE_PERMISSION_MESSAGE,
    }

def handle_duplicate(file_path, db: Session, reason="Duplicate detected", file_hash=None):
    """Move a duplicate file to the DUPLICATE folder."""
    filename = os.path.basename(file_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_name = f"{timestamp}_{filename}"
    dest_path = os.path.join(DUPLICATE_ROOT, dest_name)
    
    if duplicate_permission_ignored_today(db, file_path, file_hash=file_hash):
        logger.debug(f"Duplicate move permission failure already logged today. Skipping retry for {file_path}")
        return {
            "status": "ignored_permission",
            "action": DUPLICATE_MOVE_FAILED_PERMISSION,
            "operator_message": DUPLICATE_PERMISSION_MESSAGE,
        }
    
    try:
        shutil.move(file_path, dest_path)
        logger.info(f"Moved duplicate {filename} to {dest_path}")
        
        # Log to audit logs
        _log_duplicate_event(
            db,
            "DUPLICATE_MOVE",
            "DUPLICATE",
            _duplicate_metadata(file_path, reason, file_hash=file_hash, dest_path=dest_path)
        )
        return {"status": "moved", "action": "DUPLICATE_MOVE", "dest_path": dest_path}
    except Exception as e:
        if _is_access_denied(e):
            metadata = _duplicate_metadata(file_path, reason, file_hash=file_hash, dest_path=dest_path, error=e)
            _log_duplicate_event(db, DUPLICATE_MOVE_FAILED_PERMISSION, "IGNORED_UNTIL_PERMISSION_FIXED", metadata)
            logger.error(f"{DUPLICATE_PERMISSION_MESSAGE} File left untouched: {file_path}")
            return {
                "status": "permission_failed",
                "action": DUPLICATE_MOVE_FAILED_PERMISSION,
                "operator_message": DUPLICATE_PERMISSION_MESSAGE,
                "error": str(e),
            }
        logger.error(f"Failed to move duplicate {file_path}: {e}")
        return {"status": "failed", "action": "DUPLICATE_MOVE_FAILED", "error": str(e)}

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
