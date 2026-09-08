import os
import sys
from sqlalchemy.orm import Session
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database import SessionLocal
from backend.models import Bill

WATCH_PATH = r"C:\Aradhana\InvoicePDFs"
ARCHIVE_ROOT = r"C:\Aradhana\OLD"
DUPLICATE_ROOT = r"C:\Aradhana\DUPLICATE"

def count_files(directory):
    if not os.path.exists(directory):
        return 0
    count = 0
    for root, dirs, files in os.walk(directory):
        count += len([f for f in files if f.lower().endswith(".pdf")])
    return count

def run_diagnostic():
    print("=== Invoice Folder Lifecycle Diagnostic ===")
    
    # 1. Physical counts
    active_files = count_files(WATCH_PATH)
    archived_files = count_files(ARCHIVE_ROOT)
    duplicate_files = count_files(DUPLICATE_ROOT)
    
    print(f"Physical Files on Disk:")
    print(f" - Active Folder:    {active_files}")
    print(f" - Archive Folder:   {archived_files}")
    print(f" - Duplicate Folder: {duplicate_files}")
    print("-" * 40)
    
    # 2. Database Status
    db = SessionLocal()
    try:
        total_bills = db.query(Bill).count()
        cleared = db.query(Bill).filter(Bill.status == "Green").count()
        pending = db.query(Bill).filter(Bill.status == "Yellow").count()
        review = db.query(Bill).filter(Bill.status == "Blue").count()
        error = db.query(Bill).filter(Bill.status == "Red").count()
        
        # Files in database but missing on disk
        missing_files = 0
        bills = db.query(Bill).all()
        for b in bills:
            if b.pdf_path and not os.path.exists(b.pdf_path):
                missing_files += 1
                
        print(f"Database Stats:")
        print(f" - Total Invoices:   {total_bills}")
        print(f" - Cleared (Green):  {cleared}")
        print(f" - Pending (Yellow): {pending}")
        print(f" - Review (Blue):    {review}")
        print(f" - Error (Red):      {error}")
        print(f" - Missing Files:    {missing_files}")
        
    finally:
        db.close()

if __name__ == "__main__":
    run_diagnostic()
