from pathlib import Path
import sys
import os
from sqlalchemy import func, or_

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal
from backend.models import Bill, Payment

def run_audit():
    db = SessionLocal()
    try:
        print("\n=== PRODUCTION DATA AUDIT ===")
        
        # 1. Counts
        total_bills = db.query(Bill).count()
        test_bills = db.query(Bill).filter(Bill.is_test_data == True).count()
        real_bills = db.query(Bill).filter(Bill.is_test_data == False).count()
        
        print(f"Total Bills in DB: {total_bills}")
        print(f"Test/Synthetic Bills: {test_bills} (Excluded from Dashboard)")
        print(f"Real Production Bills: {real_bills}")
        
        # 2. Zero Amount Real Bills
        zero_real = db.query(Bill).filter(Bill.is_test_data == False, Bill.amount == 0).count()
        print(f"Real Bills with ₹0 Total: {zero_real}")
        
        # 3. Sample Real Invoices (Top 10)
        print("\nTop 10 Real Invoices (Live Feed Simulation):")
        print(f"{'Inv No':<12} | {'Total':>10} | {'Purchase':>10} | {'Advance':>10} | {'Net Pay':>10} | {'Paid':>10} | {'Remain':>10}")
        print("-" * 85)
        
        bills = db.query(Bill).filter(Bill.is_test_data == False).order_by(Bill.created_at.desc()).limit(10).all()
        for b in bills:
            invoice_total = float(b.amount or 0)
            cust_purc = float(b.customer_purchase_amount or 0)
            advance = float(b.advance_amount or 0)
            net_payable = invoice_total - cust_purc - advance
            paid = float(b.cash_received or 0) + float(b.bank_received or 0) + float(b.card_received or 0) + float(b.sms_confirmed_amount or 0) + float(b.email_confirmed_amount or 0)
            remaining = float(b.remaining_amount or 0)
            
            print(f"{b.bill_number:<12} | {invoice_total:10.2f} | {cust_purc:10.2f} | {advance:10.2f} | {net_payable:10.2f} | {paid:10.2f} | {remaining:10.2f}")

        # 4. Test Data Details
        if test_bills > 0:
            print("\nExcluded Test Data Sample:")
            t_bills = db.query(Bill).filter(Bill.is_test_data == True).limit(5).all()
            for tb in t_bills:
                print(f" - {tb.bill_number} (Customer: {tb.customer_name}, Created: {tb.created_at})")

    finally:
        db.close()

if __name__ == "__main__":
    run_audit()
