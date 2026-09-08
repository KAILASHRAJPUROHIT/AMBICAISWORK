from pathlib import Path
import sys
import os
import re
from datetime import datetime

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal
from backend.models import Bill
from backend.pdf_ingestion import parse_pdf

def repopulate_timestamps():
    db = SessionLocal()
    try:
        bills = db.query(Bill).filter(Bill.is_test_data == False).all()
        print(f"Repopulating timestamps for {len(bills)} bills...")
        
        for b in bills:
            if not b.pdf_path or not os.path.exists(b.pdf_path):
                print(f" - Skipping {b.bill_number}: PDF not found at {b.pdf_path}")
                continue
                
            invoice_data = parse_pdf(b.pdf_path)
            if invoice_data and invoice_data.get("invoice_generated_at"):
                gen_at = invoice_data["invoice_generated_at"]
                print(f" - Updating {b.bill_number}: Generated At = {gen_at}")
                b.invoice_generated_at = gen_at
            else:
                # Fallback to file mtime if parse failed or metadata missing
                mtime = os.path.getmtime(b.pdf_path)
                gen_at = datetime.fromtimestamp(mtime)
                print(f" - Updating {b.bill_number} (mtime): Generated At = {gen_at}")
                b.invoice_generated_at = gen_at
        
        db.commit()
        print("Success.")
    finally:
        db.close()

if __name__ == "__main__":
    repopulate_timestamps()
