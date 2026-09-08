from backend.database import SessionLocal
from backend.models import Bill
from sqlalchemy import or_

def mark_test_data():
    db = SessionLocal()
    try:
        # 1. Audit and Mark
        test_bills = db.query(Bill).filter(
            or_(
                Bill.bill_number.like("TEST-%"),
                Bill.bill_number.like("BILL-%"),
                Bill.customer_name == "User 1",
                Bill.customer_name == "None" # Some TEST-ARCH had None
            )
        ).all()
        
        print(f"Found {len(test_bills)} test/synthetic records.")
        for b in test_bills:
            print(f"Marking ID {b.id} ({b.bill_number}) as TEST DATA.")
            b.is_test_data = True
            
        db.commit()
        print("Success.")
    finally:
        db.close()

if __name__ == "__main__":
    mark_test_data()
