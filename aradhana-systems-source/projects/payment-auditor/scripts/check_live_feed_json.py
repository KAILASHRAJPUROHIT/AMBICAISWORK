from backend.database import SessionLocal
from backend.models import Bill
import json

def check_live_feed():
    db = SessionLocal()
    try:
        bills = db.query(Bill).order_by(Bill.created_at.desc()).limit(5).all()
        for b in bills:
            # Manual dict conversion to see what FastAPI/JSONResponse would see
            data = {
                "id": b.id,
                "bill_number": b.bill_number,
                "amount": float(b.amount) if b.amount else 0.0,
                "total_amount": float(b.total_amount) if b.total_amount else 0.0,
                "customer_name": b.customer_name
            }
            print(json.dumps(data, indent=2))
    finally:
        db.close()

if __name__ == "__main__":
    check_live_feed()
