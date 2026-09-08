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
from backend.models import Bill, Payment

def reparse_real_invoices():
    db = SessionLocal()
    try:
        bills = db.query(Bill).filter(Bill.is_test_data == False).all()
        print(f"Reparsing {len(bills)} real invoices...")
        
        for b in bills:
            text = b.raw_extracted_text or ""
            if not text:
                continue
                
            lines = text.split("\n")
            in_narration = False
            cust_purc_total = 0.0
            advance_total = 0.0
            
            for line in lines:
                line_upper = line.upper()
                if "TOTAL" in line_upper and re.search(r"\d+\.\d{2}", line):
                    in_narration = True
                    continue
                if "ACK NO" in line_upper:
                    in_narration = False
                    break
                    
                if in_narration:
                    amt_match = re.search(r"([\d,]+\.\d{2})", line)
                    if amt_match:
                        amt = float(amt_match.group(1).replace(",", ""))
                        if "ADVANCE" in line_upper:
                            advance_total += amt
                        elif any(x in line_upper for x in ["OLD GOLD", "CUST PURC", "PURCHASE"]):
                            cust_purc_total += amt
            
            print(f"Update {b.bill_number}: Purc={cust_purc_total}, Adv={advance_total}")
            b.customer_purchase_amount = cust_purc_total
            b.advance_amount = advance_total
            
            # Recalculate remaining
            # paid = cash + bank + card + sms + email
            # We don't change paid here, but we should ensure remaining is total - cash - adv - purc - bank...
            # The ingestion logic used: remaining = total - (cash + adv + purc)
            # which is essentially "Unconfirmed amount"
            b.remaining_amount = float(b.amount) - (float(b.cash_received or 0) + float(advance_total) + float(cust_purc_total))
            if b.remaining_amount < 0: b.remaining_amount = 0
            
        db.commit()
        print("Done.")
    finally:
        db.close()

if __name__ == "__main__":
    reparse_real_invoices()
