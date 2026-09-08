import os

filepath = r"C:\Users\kaila\aradhana-payment-auditor\aradhana-payment-auditor\backend\review_api.py"

with open(filepath, "a", encoding="utf-8") as f:
    f.write("""

@app.get("/api/dashboard/today-bills")
async def get_dashboard_today_bills(db: Session = Depends(get_db)):
    from backend.models import Bill
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    bills = db.query(Bill).filter(
        Bill.is_test_data == False,
        ~Bill.bill_number.like('TEST-%'),
        ~Bill.bill_number.like('ARCH-%'),
        func.date(func.coalesce(Bill.invoice_date, Bill.created_at)) == today_str
    ).order_by(Bill.invoice_date.desc(), Bill.created_at.desc()).all()
    
    results = []
    for b in bills:
        # Determine status
        status_text = b.status_text or b.status or "Pending"
        results.append({
            "id": b.id,
            "bill_number": b.bill_number,
            "customer_name": b.customer_name or "Unknown",
            "amount": float(b.amount) if b.amount else 0.0,
            "payment_mode": "MULTIPLE" if b.advance_source == "MIXED" else (b.advance_source or "UNKNOWN"),
            "status": status_text,
            "invoice_date": b.invoice_date.isoformat() if b.invoice_date else (b.created_at.isoformat() if b.created_at else None)
        })
    return results

@app.get("/api/dashboard/today-payments")
async def get_dashboard_today_payments(db: Session = Depends(get_db)):
    from backend.models import Payment as PaymentModel, Bill
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    payments = db.query(PaymentModel, Bill).join(
        Bill, PaymentModel.bill_id == Bill.id
    ).filter(
        Bill.is_test_data == False,
        ~Bill.bill_number.like('TEST-%'),
        func.date(func.coalesce(PaymentModel.payment_date, PaymentModel.created_at)) == today_str
    ).order_by(PaymentModel.payment_date.desc(), PaymentModel.created_at.desc()).all()
    
    results = []
    for p, b in payments:
        results.append({
            "id": p.id,
            "invoice_number": b.bill_number,
            "customer_name": b.customer_name or "Unknown",
            "amount_received": float(p.amount) if p.amount else 0.0,
            "payment_mode": p.mode or "UNKNOWN",
            "utr_reference": p.utr_reference or p.cheque_number or "N/A",
            "payment_date": p.payment_date.isoformat() if p.payment_date else (p.created_at.isoformat() if p.created_at else None),
            "status": p.status or "Pending"
        })
    return results
""")

print("Endpoints added to review_api.py")
