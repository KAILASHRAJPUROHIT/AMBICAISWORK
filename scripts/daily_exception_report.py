from pathlib import Path
import sys
import os
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, func

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal
from backend.models import Bill, Payment, BankAlert, Cheque, AuditLog

def generate_report():
    db = SessionLocal()
    try:
        print(f"\n{'='*60}")
        print(f"ARADHANA PAYMENT AUDITOR - DAILY EXCEPTION REPORT")
        print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        # 1. Duplicate UTRs
        print("1. DUPLICATE UTR DETECTION")
        duplicates = db.query(Payment.utr_reference, func.count(Payment.id)).\
            filter(Payment.utr_reference != None).\
            group_by(Payment.utr_reference).\
            having(func.count(Payment.id) > 1).all()
        
        if duplicates:
            for utr, count in duplicates:
                bills = db.query(Bill.bill_number).join(Payment).filter(Payment.utr_reference == utr).all()
                bill_nos = [b[0] for b in bills]
                print(f"  [CRITICAL] UTR {utr} used {count} times across bills: {', '.join(bill_nos)}")
        else:
            print("  No duplicate UTRs detected.")
        print("-" * 60)

        # 2. Ambiguous Matches (Recently flagged)
        print("2. AMBIGUOUS AMOUNT MATCHES")
        ambiguous = db.query(Bill).filter(Bill.status_text.like("%AMBIGUOUS_AMOUNT_MATCH%")).all()
        if ambiguous:
            for b in ambiguous:
                print(f"  [REVIEW] Bill {b.bill_number}: ₹{b.amount} - {b.status_text}")
        else:
            print("  No ambiguous matches found.")
        print("-" * 60)

        # 3. Partial Payments
        print("3. PARTIAL PAYMENTS")
        partial = db.query(Bill).filter(Bill.remaining_amount > 0, Bill.is_test_data == False).all()
        if partial:
            for b in partial:
                paid = float(b.amount) - float(b.remaining_amount)
                print(f"  [PENDING] Bill {b.bill_number}: Total ₹{b.amount}, Paid ₹{paid:.2f}, Remaining ₹{b.remaining_amount}")
        else:
            print("  No partial payments pending.")
        print("-" * 60)

        # 4. Advance Verification Pending
        print("4. ADVANCE VERIFICATION PENDING")
        adv_pending = db.query(Bill).filter(
            or_(
                Bill.status_text == "ADVANCE_REQUIRES_VERIFICATION",
                Bill.status_text == "ADVANCE_PAYMENT_TYPE_UNKNOWN",
                Bill.status == "Purple"
            )
        ).all()
        if adv_pending:
            for b in adv_pending:
                print(f"  [REVIEW] Bill {b.bill_number}: Advance ₹{b.advance_amount} requires verification ({b.status_text}).")
        else:
            print("  No advance verifications pending.")
        print("-" * 60)

        # 5. Cheque Ageing
        print("5. CHEQUE AGEING")
        now = datetime.now()
        cheques = db.query(Cheque).filter(Cheque.status != "Green").all()
        if cheques:
            for c in cheques:
                days = (now - c.created_at).days
                ageing = "0-3 days"
                if 4 <= days <= 7: ageing = "4-7 days [YELLOW]"
                elif days > 7: ageing = ">7 days [CRITICAL]"
                print(f"  [TRACKING] Cheque {c.cheque_number}: ₹{c.amount}, Age: {days} days ({ageing})")
        else:
            print("  No cheques awaiting clearance.")
        print("-" * 60)

        # 6. Delivery Before Payment
        print("6. DELIVERY BEFORE PAYMENT CASES")
        delivery_risk = db.query(Bill).filter(Bill.is_delivered == True, Bill.remaining_amount > 0).all()
        if delivery_risk:
            for b in delivery_risk:
                print(f"  [HIGH RISK] Bill {b.bill_number}: Goods delivered before full payment. Balance: ₹{b.remaining_amount}")
        else:
            print("  No high-risk delivery cases.")
        print("-" * 60)

        # 7. Reversals / Bounces
        print("7. REVERSALS AND BOUNCES")
        reversals = db.query(Bill).filter(Bill.reversal_date != None).all()
        if reversals:
            for b in reversals:
                print(f"  [CRITICAL] Bill {b.bill_number}: Reversal on {b.reversal_date}. Reason: {b.reversal_reason}")
        else:
            print("  No reversals or bounces reported.")
        print("=" * 60 + "\n")

    finally:
        db.close()

if __name__ == "__main__":
    generate_report()
