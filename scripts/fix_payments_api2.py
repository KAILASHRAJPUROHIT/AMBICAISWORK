import re

filepath = r"C:\Users\kaila\aradhana-payment-auditor\aradhana-payment-auditor\backend\review_api.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

new_payments_endpoint = """@app.get("/api/dashboard/today-payments")
async def get_dashboard_today_payments(db: Session = Depends(get_db)):
    from backend.models import Payment as PaymentModel
    from backend.models import Bill
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    payments = db.query(PaymentModel, Bill).join(Bill, PaymentModel.bill_id == Bill.id).filter(
        Bill.is_test_data == False,
        ~Bill.bill_number.like('TEST-%'),
        func.date(func.coalesce(PaymentModel.payment_date, func.datetime(PaymentModel.created_at, 'localtime'))) == today_str
    ).order_by(PaymentModel.payment_date.desc(), PaymentModel.created_at.desc()).all()
    
    results = []
    for p, b in payments:
        status_text = p.status or "Unknown"
        results.append({
            "id": p.id,
            "invoice_number": b.bill_number,
            "customer_name": b.customer_name or "Unknown",
            "amount_received": float(p.amount) if p.amount else 0.0,
            "payment_mode": p.mode or "Unknown",
            "utr_reference": p.utr_reference or p.cheque_number or "N/A",
            "payment_date": p.payment_date.isoformat() if p.payment_date else None,
            "status": status_text
        })
    return JSONResponse(content=results)"""

# Use regex to replace the old get_dashboard_today_payments
pattern = r'@app\.get\("/api/dashboard/today-payments"\)\nasync def get_dashboard_today_payments.*?return JSONResponse\(content=results\)'

content = re.sub(pattern, new_payments_endpoint, content, flags=re.DOTALL)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Payments API patched")
