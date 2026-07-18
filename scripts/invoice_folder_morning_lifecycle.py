from pathlib import Path
import sys
import os
import shutil
import argparse
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import json

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal
from backend.models import Bill, AuditLog, Payment
from backend.pdf_ingestion import process_invoice, get_file_hash, parse_pdf

# Configuration
SOURCE_PATH = r"\\PC2\AradhanaInvoicePDFs"
ARCHIVE_ROOT = r"C:\Aradhana\OLD"
DUPLICATE_ROOT = r"C:\Aradhana\DUPLICATE"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MorningLifecycle")

def run_lifecycle(execute=False):
    mode_str = "EXECUTE" if execute else "DRY-RUN"
    logger.info(f"=== Starting Morning Lifecycle ({mode_str}) ===")
    
    db = SessionLocal()
    try:
        # Phase 1: Full Import/Re-import
        if not os.path.exists(SOURCE_PATH):
            logger.error(f"Source path not found: {SOURCE_PATH}")
            return
            
        pdf_files = [f for f in os.listdir(SOURCE_PATH) if f.lower().endswith(".pdf")]
        logger.info(f"Found {len(pdf_files)} PDFs in source.")
        
        invoices_before = db.query(Bill).count()
        
        # Always try to import first
        for pdf in pdf_files:
            full_path = os.path.join(SOURCE_PATH, pdf)
            # process_invoice handles deduplication and status update internally
            process_invoice(full_path)
            
        invoices_after = db.query(Bill).count()
        newly_imported = invoices_after - invoices_before
        logger.info(f"Import Phase: {newly_imported} new invoices imported.")
        
        # Phase 2: Safety Guardrail
        # Requirement: If PDFs found > DB imported invoices, do not archive yet.
        # This usually means some files failed to parse or ingest.
        if len(pdf_files) > invoices_after:
            logger.warning(f"Safety Halt: {len(pdf_files)} PDFs on disk but only {invoices_after} in DB. Check for ingestion failures.")
            # return # User said "do not archive yet" - so we stop here.
            # Actually, the user says "do not archive yet" - let's see if we should continue for duplicates.
            # Usually better to stop archival to avoid moving files that aren't in DB.
            # We will continue for analysis but block moves if execute is True.
        
        # Phase 3: Categorization
        stats = {
            "found": len(pdf_files),
            "imported": newly_imported,
            "duplicates": 0,
            "blocked": 0,
            "moved_old": 0,
            "moved_dup": 0
        }
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        yesterday_end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        for pdf in pdf_files:
            full_path = os.path.join(SOURCE_PATH, pdf)
            file_hash = get_file_hash(full_path)
            
            # Check for exact duplicate in DB
            # Rule 4: PDF hash same OR invoice number, date, customer, total all match 100%
            is_dup = False
            reason = ""
            
            # Hash check
            bill_by_hash = db.query(Bill).filter(Bill.pdf_hash == file_hash).first()
            if bill_by_hash and bill_by_hash.pdf_path != full_path:
                is_dup = True
                reason = "Exact Hash Match"
            
            # 4-point match check
            if not is_dup:
                parsed = parse_pdf(full_path)
                if parsed:
                    dup_bill = db.query(Bill).filter(
                        Bill.bill_number == parsed["bill_number"],
                        Bill.invoice_date == parsed["invoice_date"],
                        Bill.customer_name == (parsed.get("customer_name") or "Unknown"),
                        Bill.amount == parsed["total_amount"]
                    ).first()
                    
                    if dup_bill and dup_bill.pdf_path != full_path:
                        is_dup = True
                        reason = "4-point Identity Match"
            
            if is_dup:
                stats["duplicates"] += 1
                if execute:
                    dest_dir = os.path.join(DUPLICATE_ROOT, today_str)
                    os.makedirs(dest_dir, exist_ok=True)
                    dest_path = os.path.join(dest_dir, pdf)
                    shutil.move(full_path, dest_path)
                    stats["moved_dup"] += 1
                    logger.info(f"Moved Duplicate: {pdf} -> {dest_path} ({reason})")
                    
                    log = AuditLog(
                        entity_type="FILE",
                        entity_id=0,
                        action="DUPLICATE_MOVE",
                        old_status="SOURCE",
                        new_status="DUPLICATE",
                        actor="MORNING_LIFECYCLE",
                        metadata_json=json.dumps({"src": full_path, "dst": dest_path, "reason": reason})
                    )
                    db.add(log)
                else:
                    logger.info(f"DRY-RUN: Would move duplicate {pdf} ({reason})")
                continue
                
            # Archival check (Non-duplicates)
            bill = db.query(Bill).filter(Bill.pdf_path == full_path).first()
            if not bill:
                # If it's not in DB and not a duplicate, it's a parse failure or something.
                # Do not move it.
                stats["blocked"] += 1
                logger.warning(f"Blocked (Not in DB): {pdf}")
                continue
                
            # Rule 7: Do not move PDFs whose invoice is PENDING, PARTIAL_PAID, REVIEW_REQUIRED
            # Yellow = Pending, Blue = Review, Red = Error
            # Green = Cleared
            if bill.status != "Green":
                stats["blocked"] += 1
                logger.info(f"Blocked (Status={bill.status}): {pdf}")
                continue
                
            # Only archive if it's from yesterday or earlier
            if bill.invoice_date and bill.invoice_date >= yesterday_end:
                stats["blocked"] += 1
                logger.info(f"Blocked (Today's Invoice): {pdf}")
                continue
                
            # Rule 3: Guardrail check
            if len(pdf_files) > invoices_after:
                stats["blocked"] += 1
                logger.warning(f"Blocked (Safety Halt - DB mismatch): {pdf}")
                continue

            # Move to OLD
            stats["moved_old"] += 1
            if execute:
                dest_dir = os.path.join(ARCHIVE_ROOT, today_str)
                os.makedirs(dest_dir, exist_ok=True)
                dest_path = os.path.join(dest_dir, pdf)
                shutil.move(full_path, dest_path)
                bill.pdf_path = dest_path # Update DB path
                logger.info(f"Archived: {pdf} -> {dest_path}")
                
                log = AuditLog(
                    entity_type="BILL",
                    entity_id=bill.id,
                    action="ARCHIVE",
                    old_status="Green",
                    new_status="ARCHIVED",
                    actor="MORNING_LIFECYCLE",
                    metadata_json=json.dumps({"dst": dest_path})
                )
                db.add(log)
            else:
                logger.info(f"DRY-RUN: Would archive {pdf}")

        if execute:
            db.commit()
            
        print("\n=== Lifecycle Results ===")
        print(f"PDFs found:           {stats['found']}")
        print(f"Imported:             {stats['imported']}")
        print(f"Duplicates:           {stats['duplicates']}")
        print(f"Blocked from archive: {stats['blocked']}")
        print(f"Moved to OLD:         {stats['moved_old']}")
        print(f"Moved to DUPLICATE:   {stats['moved_dup']}")
        
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Invoice Folder Morning Lifecycle")
    parser.add_argument("--dry-run", action="store_true", help="Report only, do not move files (default)", default=True)
    parser.add_argument("--execute", action="store_true", help="Perform actual file moves")
    
    args = parser.parse_args()
    
    # If --execute is passed, it overrides dry-run
    exec_mode = args.execute
    
    run_lifecycle(execute=exec_mode)
