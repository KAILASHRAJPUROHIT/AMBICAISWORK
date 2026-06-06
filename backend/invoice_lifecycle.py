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

PDF_RETENTION_DAYS = int(os.getenv("PDF_RETENTION_DAYS", "365"))
AUDIT_RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "365"))
WATCH_PATH = r"C:\Aradhana\InvoicePDFs"
ARCHIVE_ROOT = r"C:\Aradhana\OLD"
DUPLICATE_ROOT = os.getenv("DUPLICATE_ARCHIVE_PATH", r"C:\Aradhana\DUPLICATE")
DUPLICATE_FALLBACK_ROOT = os.getenv("DUPLICATE_ARCHIVE_FALLBACK_PATH")
DUPLICATE_MOVE_FAILED_PERMISSION = "DUPLICATE_MOVE_FAILED_PERMISSION"
DUPLICATE_QUARANTINE_COPY = "DUPLICATE_QUARANTINE_COPY"
DUPLICATE_PERMISSION_MESSAGE = "Duplicate PDF detected but archive move failed due to Windows share permission."
DUPLICATE_PERMISSION_OPERATOR_MESSAGE = "Duplicate archive move blocked by permission. Original retained."

# Ensure directories exist
for path in [WATCH_PATH, ARCHIVE_ROOT, DUPLICATE_ROOT, DUPLICATE_FALLBACK_ROOT]:
    if path:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as exc:
            logger.warning(f"Could not create lifecycle directory {path}: {exc}")

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
        "operator_message": DUPLICATE_PERMISSION_OPERATOR_MESSAGE if error else None,
        "pdf_retention_days": PDF_RETENTION_DAYS,
        "audit_retention_days": AUDIT_RETENTION_DAYS,
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

def is_retention_protected(created_at=None, file_path=None, retention_days=PDF_RETENTION_DAYS) -> bool:
    cutoff_seconds = retention_days * 24 * 60 * 60
    now = datetime.now()
    if created_at and (now - created_at).total_seconds() < cutoff_seconds:
        return True
    if file_path and os.path.exists(file_path):
        file_age_seconds = time.time() - os.path.getmtime(file_path)
        return file_age_seconds < cutoff_seconds
    return False

def assert_can_delete_pdf(file_path, created_at=None):
    if is_retention_protected(created_at=created_at, file_path=file_path, retention_days=PDF_RETENTION_DAYS):
        raise PermissionError(f"PDF retention guard blocked deletion before {PDF_RETENTION_DAYS} days: {file_path}")

def assert_can_purge_audit(created_at):
    if is_retention_protected(created_at=created_at, retention_days=AUDIT_RETENTION_DAYS):
        raise PermissionError(f"Audit retention guard blocked purge before {AUDIT_RETENTION_DAYS} days")

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
        AuditLog.action.in_(["DUPLICATE_MOVE", DUPLICATE_QUARANTINE_COPY, DUPLICATE_MOVE_FAILED_PERMISSION])
    ).all()
    return {
        "total_duplicates": len(logs),
        "failed_moves": sum(1 for log in logs if log.action == DUPLICATE_MOVE_FAILED_PERMISSION),
        "fallback_quarantine_copies": sum(1 for log in logs if log.action == DUPLICATE_QUARANTINE_COPY),
        "ignored_until_permission_fixed": sum(1 for log in logs if log.action == DUPLICATE_MOVE_FAILED_PERMISSION),
        "operator_message": DUPLICATE_PERMISSION_OPERATOR_MESSAGE,
        "pdf_retention_days": PDF_RETENTION_DAYS,
        "audit_retention_days": AUDIT_RETENTION_DAYS,
    }

def _verified_copy(src_path, dest_path):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    shutil.copy2(src_path, dest_path)
    if not os.path.exists(dest_path):
        raise IOError(f"Duplicate archive copy missing after copy: {dest_path}")
    if os.path.getsize(src_path) != os.path.getsize(dest_path):
        raise IOError(f"Duplicate archive copy size mismatch: {dest_path}")

def _copy_to_fallback_quarantine(file_path, filename, timestamp):
    if not DUPLICATE_FALLBACK_ROOT:
        return None
    fallback_path = os.path.join(DUPLICATE_FALLBACK_ROOT, f"{timestamp}_{filename}")
    _verified_copy(file_path, fallback_path)
    return fallback_path

def handle_duplicate(file_path, db: Session, reason="Duplicate detected", file_hash=None):
    """Archive a duplicate file without deleting unless the archive copy is verified."""
    filename = os.path.basename(file_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_name = f"{timestamp}_{filename}"
    dest_path = os.path.join(DUPLICATE_ROOT, dest_name)
    
    if duplicate_permission_ignored_today(db, file_path, file_hash=file_hash):
        logger.debug(f"Duplicate move permission failure already logged today. Skipping retry for {file_path}")
        return {
            "status": "ignored_permission",
            "action": DUPLICATE_MOVE_FAILED_PERMISSION,
            "operator_message": DUPLICATE_PERMISSION_OPERATOR_MESSAGE,
        }
    
    try:
        _verified_copy(file_path, dest_path)
        assert_can_delete_pdf(file_path)
        os.remove(file_path)
        logger.info(f"Archived duplicate {filename} to {dest_path}")
        
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
            fallback_path = None
            fallback_error = None
            try:
                fallback_path = _copy_to_fallback_quarantine(file_path, filename, timestamp)
            except Exception as fallback_exc:
                fallback_error = str(fallback_exc)

            metadata = _duplicate_metadata(file_path, reason, file_hash=file_hash, dest_path=dest_path, error=e)
            if fallback_path:
                metadata["fallback_quarantine_path"] = fallback_path
                metadata["fallback_action"] = DUPLICATE_QUARANTINE_COPY
            if fallback_error:
                metadata["fallback_error"] = fallback_error
            _log_duplicate_event(db, DUPLICATE_MOVE_FAILED_PERMISSION, "IGNORED_UNTIL_PERMISSION_FIXED", metadata)
            logger.error(f"{DUPLICATE_PERMISSION_OPERATOR_MESSAGE} File left untouched: {file_path}")
            return {
                "status": "fallback_copied_permission_failed" if fallback_path else "permission_failed",
                "action": DUPLICATE_MOVE_FAILED_PERMISSION,
                "operator_message": DUPLICATE_PERMISSION_OPERATOR_MESSAGE,
                "error": str(e),
                "fallback_quarantine_path": fallback_path,
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
                _verified_copy(bill.pdf_path, dest_path)
                assert_can_delete_pdf(bill.pdf_path, created_at=bill.created_at)
                os.remove(bill.pdf_path)
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
