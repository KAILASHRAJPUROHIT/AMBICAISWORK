from pathlib import Path
import sys
import os

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models import Bill, BankAlert, SMSAlert, Payment
from datetime import datetime
import json

def trace_reconciliation(identifier: str):
    db = SessionLocal()
    from sqlalchemy import or_, and_
    print(f"\n{'='*60}")
    print(f"RECONCILIATION TRACE FOR: {identifier}")
    print(f"{'='*60}\n")

    # 1. Identify what we are looking for
    bill = db.query(Bill).filter(Bill.bill_number == identifier).first()
    alert = db.query(BankAlert).filter(BankAlert.utr_reference == identifier).first()
    if not alert:
        # Check SMS
        sms = db.query(SMSAlert).filter(SMSAlert.utr_reference == identifier).first()
        if sms:
            alert = db.query(BankAlert).filter(BankAlert.utr_reference == identifier).first()
            if not alert:
                print(f"Found SMS alert {identifier} but no corresponding BankAlert yet.")
                # We can mock a BankAlert from SMS for tracing if needed, 
                # but verify_payment_event works on BankAlert.

    if not bill and not alert:
        print(f"ERROR: Could not find Bill or BankAlert with identifier: {identifier}")
        db.close()
        return

    if bill:
        print(f"TARGET BILL FOUND:")
        print(f"  ID: {bill.id}")
        print(f"  Bill No: {bill.bill_number}")
        print(f"  Customer: {bill.customer_name}")
        print(f"  Amount: {bill.total_amount}")
        print(f"  Date: {bill.invoice_date}")
        print(f"  Status: {bill.status} ({bill.status_text})")
        print(f"  Ref in DB: {bill.reference_no}")
        print(f"  Remaining: {bill.remaining_amount}")
        print(f"  Bank Rcvd: {bill.bank_received}")
        print("-" * 30)

    if alert:
        print(f"TARGET PAYMENT ALERT FOUND:")
        print(f"  ID: {alert.id}")
        print(f"  UTR: {alert.utr_reference}")
        print(f"  Amount: {alert.amount}")
        print(f"  Bank: {alert.bank_name}")
        print(f"  Received: {alert.received_at}")
        print(f"  Reconciled: {alert.reconciled}")
        print("-" * 30)

    # 2. Simulate matching for an alert
    if alert:
        print("\nSIMULATING MATCHING PROCESS FOR ALERT...")
        amount = float(alert.amount)
        utr = alert.utr_reference
        received_at = alert.received_at

        from sqlalchemy import or_, and_
        matching_bills = db.query(Bill).filter(
            or_(
                and_(Bill.total_amount >= amount - 0.01, Bill.total_amount <= amount + 0.01),
                and_(Bill.remaining_amount >= amount - 0.01, Bill.remaining_amount <= amount + 0.01)
            )
        ).all()

        print(f"  Candidate bills with same amount (₹{amount}): {len(matching_bills)}")
        
        if not matching_bills and utr:
            bill_by_utr = db.query(Bill).filter(Bill.reference_no == utr).first()
            if bill_by_utr:
                print(f"  No amount match, but found Bill by UTR: {bill_by_utr.bill_number}")
                matching_bills = [bill_by_utr]

        scored_candidates = []
        for b in matching_bills:
            score = 0
            details = []
            
            # A. UTR Match (+100)
            if utr and b.reference_no and utr == b.reference_no:
                score += 100
                details.append("UTR Match (+100)")
            elif utr and b.reference_no:
                details.append(f"UTR Mismatch (Alert: {utr}, Bill: {b.reference_no})")
                
            # B. Customer Name Match (+50)
            if b.customer_name and b.customer_name.lower() != "unknown":
                name_tokens = [t for t in b.customer_name.lower().replace("(", " ").replace(")", " ").split() if len(t) > 2]
                raw_text = alert.raw_text.lower()
                matches = sum(1 for t in name_tokens if t in raw_text)
                if len(name_tokens) > 0 and (matches / len(name_tokens)) >= 0.5:
                    score += 50
                    details.append(f"Name Match (+50, {matches}/{len(name_tokens)} tokens)")
                else:
                    details.append(f"Name Match Fail ({matches}/{len(name_tokens)} tokens)")
            
            # C. Date Proximity (+30)
            if b.invoice_date:
                days_diff = (received_at.date() - b.invoice_date.date()).days
                if 0 <= days_diff <= 3:
                    score += 30
                    details.append(f"Date Proximity (+30, {days_diff} days diff)")
                elif -2 <= days_diff <= 7:
                    score += 10
                    details.append(f"Date Proximity (+10, {days_diff} days diff)")
                else:
                    details.append(f"Date Too Far ({days_diff} days diff)")

            # D. Bank Name Match (+20)
            if b.bank_name and alert.bank_name and b.bank_name.lower() == alert.bank_name.lower():
                score += 20
                details.append(f"Bank Match (+20, {alert.bank_name})")

            scored_candidates.append({
                "bill_no": b.bill_number,
                "score": score,
                "details": details
            })

        print("\nSCORING RESULTS:")
        for res in scored_candidates:
            print(f"  Bill {res['bill_no']}: Score {res['score']}")
            for d in res['details']:
                print(f"    - {d}")

        if not scored_candidates:
            print("  NO CANDIDATES EVALUATED.")
    
    # 3. If we searched for a bill, look for candidate alerts
    if bill:
        print("\nSEARCHING FOR CANDIDATE PAYMENTS FOR BILL...")
        amount = float(bill.total_amount)
        rem_amount = float(bill.remaining_amount or amount)
        
        candidate_alerts = db.query(BankAlert).filter(
            or_(
                and_(BankAlert.amount >= amount - 0.01, BankAlert.amount <= amount + 0.01),
                and_(BankAlert.amount >= rem_amount - 0.01, BankAlert.amount <= rem_amount + 0.01)
            )
        ).all()
        
        print(f"  Candidate alerts with same amount: {len(candidate_alerts)}")
        for a in candidate_alerts:
            print(f"    - ID: {a.id}, Bank: {a.bank_name}, Amount: {a.amount}, UTR: {a.utr_reference}, Date: {a.received_at}")

    db.close()
    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/reconciliation_trace.py <invoice_no_or_utr>")
        sys.exit(1)
    
    trace_reconciliation(sys.argv[1])
