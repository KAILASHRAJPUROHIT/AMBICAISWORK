from pathlib import Path
import sys
import os
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal
from backend.models import Bill, Payment, BankAlert, SMSAlert

def run_diagnostic():
    print("=== Reconciliation Diagnostic Report ===")
    print(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 80)
    
    db = SessionLocal()
    try:
        # Today's invoices (Strict invoice_date logic)
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_str = now.strftime("%Y-%m-%d")
        
        from sqlalchemy import func
        bills = db.query(Bill).filter(func.date(Bill.invoice_date) == today_str, Bill.is_test_data == False).all()
        imported_today = db.query(Bill).filter(Bill.created_at >= today_start, Bill.is_test_data == False).all()
        
        print(f"Bills Dated Today: {len(bills)}")
        print(f"Bills Imported Today: {len(imported_today)}")
        
        if not bills and not imported_today:
            print("No invoices found for today.")
            return

        # Show dated today first
        display_bills = bills if bills else imported_today
        print(f"\n{'Inv No':<15} | {'Total':>10} | {'CustPurc':>10} | {'Advance':>10} | {'Net Pay':>10} | {'Status':<15}")
        print("-" * 80)
        
        count = 0
        for bill in bills:
            payments = db.query(Payment).filter(Payment.bill_id == bill.id).all()
            
            cust_purc = sum(p.amount for p in payments if p.mode == "OLD_GOLD_EXCHANGE")
            advance = sum(p.amount for p in payments if p.mode == "ADVANCE")
            net_payable = float(bill.total_amount) - float(cust_purc) - float(advance)
            
            print(f"{bill.bill_number:<15} | {float(bill.total_amount):10.2f} | {float(cust_purc):10.2f} | {float(advance):10.2f} | {net_payable:10.2f} | {bill.status:<15}")
            
            count += 1
            if count >= 20:
                break
                
        # Aggregate Summary
        total_invoices = len(bills)
        green = sum(1 for b in bills if b.status == "Green")
        yellow = sum(1 for b in bills if b.status == "Yellow")
        blue = sum(1 for b in bills if b.status == "Blue")
        red = sum(1 for b in bills if b.status == "Red")
        purple = sum(1 for b in bills if b.status == "Purple")
        
        print("-" * 80)
        print(f"Total Invoices: {total_invoices}")
        print(f"Cleared (Green): {green}")
        print(f"Pending (Yellow): {yellow}")
        print(f"Review (Blue): {blue}")
        print(f"Ambiguous/Unknown (Purple): {purple}")
        print(f"Error (Red): {red}")
        
    finally:
        db.close()

if __name__ == "__main__":
    run_diagnostic()
