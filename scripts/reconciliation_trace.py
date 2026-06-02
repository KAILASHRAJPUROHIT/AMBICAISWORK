import os
import sys
import argparse
import logging
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database import SessionLocal
from backend.models import Bill, Payment, BankAlert, SMSAlert

def trace_reconciliation(invoice_no=None, utr=None):
    db = SessionLocal()
    try:
        print(f"=== Reconciliation Trace: Invoice={invoice_no}, UTR={utr} ===")
        
        # 1. Identify Target Alert
        alert = None
        if utr:
            alert = db.query(BankAlert).filter(BankAlert.utr_reference == utr).first()
            if not alert:
                print(f"Error: No BankAlert found with UTR {utr}")
                return
        
        # 2. Identify Target Bill
        bill = None
        if invoice_no:
            bill = db.query(Bill).filter(Bill.bill_number == invoice_no).first()
            if not bill:
                print(f"Error: No Bill found with Number {invoice_no}")
                # We can still proceed if we have an alert
        
        if not alert and not bill:
            print("Error: Need either an invoice number or a UTR reference.")
            return

        if alert:
            print(f"\n--- Analyzing Alert: ID={alert.id}, UTR={alert.utr_reference}, Amount={alert.amount} ---")
            print(f"Bank: {alert.bank_name}, Received: {alert.received_at}")
            
            amount = float(alert.amount)
            
            # Re-run candidate finding logic
            matching_bills = db.query(Bill).filter(
                or_(
                    and_(Bill.total_amount >= amount - 0.01, Bill.total_amount <= amount + 0.01),
                    and_(Bill.remaining_amount >= amount - 0.01, Bill.remaining_amount <= amount + 0.01)
                ),
                Bill.status != "Green"
            ).all()
            
            print(f"Found {len(matching_bills)} candidate bills by amount matching.")
            for b in matching_bills:
                print(f"  - {b.bill_number}: Total={b.total_amount}, Remaining={b.remaining_amount}, Status={b.status}")

            if not matching_bills:
                if utr:
                    bill_by_utr = db.query(Bill).filter(Bill.reference_no == utr).first()
                    if bill_by_utr:
                        print(f"Found bill {bill_by_utr.bill_number} by UTR match.")
                        matching_bills = [bill_by_utr]
            
            if not matching_bills:
                print("REJECTION: No candidate bills found for this amount/reference.")
                return

            # Scoring Simulation
            candidates_count = len(matching_bills)
            for b in matching_bills:
                score = 0
                details = []
                
                # A. UTR Match (+100)
                if utr and b.reference_no and utr == b.reference_no:
                    score += 100
                    details.append("UTR Match (+100)")
                    
                # B. Customer Name Match (+50)
                if b.customer_name and b.customer_name.lower() != "unknown":
                    name_tokens = [t for t in b.customer_name.lower().replace("(", " ").replace(")", " ").split() if len(t) > 2]
                    raw_text = alert.raw_text.lower()
                    matches = sum(1 for t in name_tokens if t in raw_text)
                    if len(name_tokens) > 0 and (matches / len(name_tokens)) >= 0.5:
                        score += 50
                        details.append(f"Name Match ({matches}/{len(name_tokens)}) (+50)")
                        
                # C. Date Proximity (+30)
                if b.invoice_date:
                    days_diff = (alert.received_at.date() - b.invoice_date.date()).days
                    if 0 <= days_diff <= 3:
                        score += 30
                        details.append(f"Date Diff {days_diff}d (+30)")
                    elif -2 <= days_diff <= 7:
                        score += 10
                        details.append(f"Date Diff {days_diff}d (+10)")
                
                # D. Bank Name Match (+20)
                if b.bank_name and alert.bank_name and b.bank_name.lower() == alert.bank_name.lower():
                    score += 20
                    details.append(f"Bank Match ({alert.bank_name}) (+20)")

                print(f"Scoring {b.bill_number}: Total Score = {score}")
                for d in details:
                    print(f"  - {d}")
                
                is_ambiguous = (candidates_count > 1 and score < 100)
                if score < 80:
                    print(f"  - RESULT: Low Confidence ({score} < 80)")
                elif is_ambiguous:
                    print(f"  - RESULT: Ambiguous (multiple candidates, score < 100)")
                else:
                    print(f"  - RESULT: Strong Match!")

        if bill:
            print(f"\n--- Analyzing Bill: {bill.bill_number}, Status={bill.status} ---")
            print(f"Total: {bill.total_amount}, Remaining: {bill.remaining_amount}")
            print(f"Customer: {bill.customer_name}, Date: {bill.invoice_date}")
            
            # Find alerts matching this bill
            amt = float(bill.remaining_amount)
            matching_alerts = db.query(BankAlert).filter(
                and_(BankAlert.amount >= amt - 0.01, BankAlert.amount <= amt + 0.01),
                BankAlert.reconciled == False
            ).all()
            
            print(f"Found {len(matching_alerts)} unreconciled alerts matching remaining amount.")
            for a in matching_alerts:
                print(f"  - Alert {a.id}: UTR={a.utr_reference}, Bank={a.bank_name}, Date={a.received_at}")

    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trace Reconciliation logic")
    parser.add_argument("--bill", help="Invoice Number")
    parser.add_argument("--utr", help="Bank Reference / UTR")
    
    args = parser.parse_args()
    trace_reconciliation(invoice_no=args.bill, utr=args.utr)
