from backend.database import SessionLocal
from backend.models import Bill

def fix_existing_advances():
    db = SessionLocal()
    try:
        bills = db.query(Bill).filter(
            Bill.advance_amount > 0,
            Bill.is_test_data == False,
            (Bill.advance_source == None) | (Bill.advance_source == "UNKNOWN")
        ).all()
        
        print(f"Fixing status for {len(bills)} bills with unverified advances...")
        for b in bills:
            print(f" - Updating {b.bill_number} to PURPLE (ADVANCE_PAYMENT_TYPE_UNKNOWN)")
            b.status = "Purple"
            b.status_text = "ADVANCE_PAYMENT_TYPE_UNKNOWN"
            b.review_required = 1
        
        db.commit()
        print("Success.")
    finally:
        db.close()

if __name__ == "__main__":
    fix_existing_advances()
