import re

filepath = r"C:\Users\kaila\aradhana-payment-auditor\aradhana-payment-auditor\backend\review_api.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Remove the endpoints from the bottom of the file
old_endpoints_pattern = r'@app\.get\("/api/dashboard/today-bills"\).*?@app\.get\("/api/dashboard/today-payments"\).*?return JSONResponse\(content=results\)'
match = re.search(old_endpoints_pattern, content, re.DOTALL)
if match:
    content = content[:match.start()] + content[match.end():]
else:
    print("Could not find the endpoints at the bottom of the file")

# 2. Add them back ABOVE the catch-all route, with the fixed date logic
new_endpoints = """
@app.get("/api/dashboard/today-bills")
async def get_dashboard_today_bills(db: Session = Depends(get_db)):
    from backend.models import Bill
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    bills = db.query(Bill).filter(
        Bill.is_test_data == False,
        ~Bill.bill_number.like('TEST-%'),
        ~Bill.bill_number.like('ARCH-%'),
        func.date(func.coalesce(Bill.invoice_date, func.datetime(Bill.created_at, 'localtime'))) == today_str
    ).order_by(Bill.invoice_date.desc(), Bill.created_at.desc()).all()
    
    results = []
    for b in bills:
        status_text = b.status_text or b.status or "Pending"
        results.append({
            "id": b.id,
            "bill_number": b.bill_number,
            "customer_name": b.customer_name or "Unknown",
            "amount": float(b.amount) if b.amount else 0.0,
            "payment_mode": "Various" if b.status == "Green" else "Pending",
            "status": status_text,
            "invoice_date": b.invoice_date.isoformat() if b.invoice_date else None
        })
    return JSONResponse(content=results)

@app.get("/api/dashboard/today-payments")
async def get_dashboard_today_payments(db: Session = Depends(get_db)):
    from backend.models import Payment as PaymentModel
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    payments = db.query(PaymentModel).filter(
        PaymentModel.is_test_data == False,
        ~PaymentModel.invoice_number.like('TEST-%'),
        func.date(func.coalesce(PaymentModel.payment_date, func.datetime(PaymentModel.created_at, 'localtime'))) == today_str
    ).order_by(PaymentModel.payment_date.desc(), PaymentModel.created_at.desc()).all()
    
    results = []
    for p in payments:
        status_text = p.status or "Unknown"
        results.append({
            "id": p.id,
            "invoice_number": p.invoice_number,
            "customer_name": p.customer_name or "Unknown",
            "amount_received": float(p.amount) if p.amount else 0.0,
            "payment_mode": p.payment_mode or "Unknown",
            "utr_reference": p.reference_number or "N/A",
            "payment_date": p.payment_date.isoformat() if p.payment_date else None,
            "status": status_text
        })
    return JSONResponse(content=results)

"""

# Insert right before @app.get("/{full_path:path}")
spa_pattern = r'(@app\.get\("/{full_path:path}"\))'
content = re.sub(spa_pattern, new_endpoints + r'\1', content)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("backend/review_api.py successfully patched")
