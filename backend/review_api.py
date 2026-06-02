import os
import json
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.auth_service import create_otp, verify_otp, create_user_session, validate_session, log_event
from backend.lan_config import lan_health_check
from backend.database import SessionLocal
from backend.models import User, LoginLog, Bill, BankAlert, SMSAlert
from backend.pdf_ingestion import start_ingestion_thread, perform_scan, ingestion_status
from backend.email_poller import start_email_poller, process_emails, email_status
from backend.sms_poller import start_sms_poller, process_sms, sms_status
from backend.api_routes import router as api_router

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Initialize FastAPI app
app = FastAPI(title="Aradhana Review API")

# Serve static files from frontend/dist if it exists
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    
    @app.exception_handler(404)
    async def fallback_to_index(request: Request, exc):
        # Only fallback for non-API routes
        if not request.url.path.startswith("/api/"):
            index_path = os.path.join(frontend_dist, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

app.include_router(api_router)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting Backend Services...")
    start_ingestion_thread()
    start_email_poller()
    start_sms_poller()

# Configuration Constants
MANUAL_REPORT_PATH = r"C:\Aradhana\PrimeExports\JSON\reconciliation_result.json"
AUDIT_LOG_DIR = r"C:\Aradhana\AuditLogs"
os.makedirs(AUDIT_LOG_DIR, exist_ok=True)

import logging
logger = logging.getLogger("ReviewAPI")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # Public endpoints that don't require session validation
    # Bootstrap endpoints for dashboard are made public to prevent "API Unavailable" on first load
    PUBLIC_ENDPOINTS = [
        "/api/auth",
        "/api/prime/dashboard/stats",
        "/api/system/share-status",
        "/api/invoices/live-feed",
        "/api/admin/system-health",
        "/api/admin/ingestion-status",
        "/api/admin/email-status",
        "/api/admin/sms-status",
        "/api/scan-now",
        "/api/email-sync-now",
        "/api/sms-sync-now",
        "/api/bank-events",
        "/api/sms-events",
        "/api/live-payment-events",
        "/api/invoices/pdf/"
    ]
    
    # LAN Health Check
    if not await lan_health_check(request):
        # We allow it for now but log it in the health check tool
        pass
    
    # Check if path is protected
    is_protected = request.url.path.startswith("/api/")
    for public_path in PUBLIC_ENDPOINTS:
        if request.url.path.startswith(public_path):
            is_protected = False
            break
            
    if is_protected:
        token = request.headers.get("X-Session-Token")
        if not token:
             print(f"--- AUTH LOG: 401 [Token Missing] Endpoint: {request.url.path} ---")
             return JSONResponse(status_code=401, content={"detail": "Session token missing"})
        
        db = SessionLocal()
        employee_id = validate_session(db, token)
        db.close()
        
        if not employee_id:
             print(f"--- AUTH LOG: 401 [Invalid/Expired Token] Endpoint: {request.url.path} ---")
             return JSONResponse(status_code=401, content={"detail": "Session expired or invalid"})
             
    response = await call_next(request)
    return response

# Models for API
class ReviewAction(BaseModel):
    invoice_no: str
    status: str
    comment: str
    accountant_id: str

@app.get("/api/system/share-status")
async def get_share_status():
    watch_path = r"Z:\Aradhana\InvoicePDFs"
    online = os.path.exists(watch_path)
    return {
        "online": online,
        "path": watch_path,
        "label": "Invoice PDF Share (PC2)",
        "status_color": "Green" if online else "Red"
    }

@app.get("/api/invoices/live-feed")
async def get_live_feed(db: Session = Depends(get_db)):
    # Returns last 50 invoices for dashboard
    bills = db.query(Bill).order_by(Bill.created_at.desc()).limit(50).all()
    return bills

@app.get("/api/prime/dashboard/stats")
async def get_dashboard_stats(db: Session = Depends(get_db)):
    from backend.reconciliation.logic import is_store_open
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 1. Base Stats
    total_bills = db.query(Bill).filter(Bill.created_at >= today_start).count()
    verified = db.query(Bill).filter(Bill.status == "Green", Bill.created_at >= today_start).count()
    review_required = db.query(Bill).filter(Bill.review_required == 1, Bill.created_at >= today_start).count()
    partial_paid = db.query(Bill).filter(Bill.status == "Blue", Bill.remaining_amount > 0, Bill.created_at >= today_start).count()
    
    # 2. Financial Metrics (Live Normalized)
    bills_today = db.query(Bill).filter(Bill.created_at >= today_start).all()
    
    total_collection = float(sum(b.total_amount for b in bills_today) or 0.0)
    
    # Cash in Hand logic: Only today after opening
    cash_confirmed = 0.0
    for b in bills_today:
        if is_store_open(b.created_at):
            cash_confirmed += float(b.cash_received or 0.0)
            
    bank_confirmed = float(sum(b.bank_received for b in bills_today) or 0.0)
    sms_confirmed = float(sum(b.sms_confirmed_amount for b in bills_today) or 0.0)
    email_confirmed = float(sum(b.email_confirmed_amount for b in bills_today) or 0.0)
    cheque_pending = float(sum(b.total_amount for b in bills_today if "CHEQUE" in (b.payment_mode or "")) or 0.0)

    return {
        "totalBillsToday": total_bills,
        "verified": verified,
        "pendingReview": review_required,
        "partialPaid": partial_paid,
        "totalCollection": total_collection,
        "cashCollection": cash_confirmed,
        "bankCollection": bank_confirmed,
        "smsConfirmed": sms_confirmed,
        "emailConfirmed": email_confirmed,
        "chequeCollection": cheque_pending,
        "matchAccuracy": round((verified / total_bills * 100), 2) if total_bills > 0 else 0.0
    }

@app.get("/api/invoices/pdf/{bill_id}")
async def get_invoice_pdf(bill_id: int, db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill or not bill.pdf_path:
        raise HTTPException(status_code=404, detail="Invoice PDF not found")
    
    if not os.path.exists(bill.pdf_path):
        raise HTTPException(status_code=404, detail="PDF file missing on disk")
        
    return FileResponse(bill.pdf_path, media_type="application/pdf")

@app.post("/api/review")
async def review_invoice(action: ReviewAction):
    # MANDATE: All actions must create audit logs
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "event": "ACCOUNTANT_REVIEW",
        "invoice_no": action.invoice_no,
        "action": action.status,
        "comment": action.comment,
        "accountant": action.accountant_id
    }
    
    log_filename = f"REVIEW_{action.invoice_no.replace('/', '_')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    log_path = os.path.join(AUDIT_LOG_DIR, log_filename)
    
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_entry, f, indent=4)
    
    return {"status": "success", "audit_log": log_path}

@app.get("/api/admin/ingestion-status")
async def get_ingestion_status():
    return ingestion_status

@app.post("/api/scan-now")
async def trigger_scan():
    # Run scan in a background thread to avoid blocking API
    import threading
    scan_thread = threading.Thread(target=perform_scan, daemon=True)
    scan_thread.start()
    return {"status": "scan_triggered", "message": "PDF rescan started in background"}

@app.get("/api/admin/email-status")
async def get_email_status():
    return email_status

@app.post("/api/email-sync-now")
async def trigger_email_sync():
    import threading
    sync_thread = threading.Thread(target=process_emails, daemon=True)
    sync_thread.start()
    return {"status": "sync_triggered", "message": "Email sync started in background"}

@app.get("/api/admin/sms-status")
async def get_sms_status():
    return sms_status

@app.post("/api/sms-sync-now")
async def trigger_sms_sync():
    import threading
    sync_thread = threading.Thread(target=process_sms, daemon=True)
    sync_thread.start()
    return {"status": "sync_triggered", "message": "SMS sync started in background"}

@app.get("/api/bank-events")
async def get_bank_events(db: Session = Depends(get_db)):
    events = db.query(BankAlert).order_by(BankAlert.received_at.desc()).limit(50).all()
    return events

@app.get("/api/sms-events")
async def get_sms_events(db: Session = Depends(get_db)):
    events = db.query(SMSAlert).order_by(SMSAlert.transaction_timestamp.desc()).limit(50).all()
    return events

@app.get("/api/live-payment-events")
async def get_live_payment_events(db: Session = Depends(get_db)):
    # Combine BankAlerts and SMSAlerts into a normalized view
    # Limit to last 50
    alerts = db.query(BankAlert).order_by(BankAlert.received_at.desc()).limit(50).all()
    sms_alerts = db.query(SMSAlert).order_by(SMSAlert.transaction_timestamp.desc()).limit(50).all()
    
    combined = []
    
    for a in alerts:
        combined.append({
            "id": f"bank_{a.id}",
            "source": "EMAIL",
            "bank": a.bank_name,
            "amount": float(a.amount),
            "reference": a.utr_reference,
            "timestamp": a.received_at.isoformat(),
            "confidence": "HIGH" if a.utr_reference and not a.utr_reference.startswith("SYNC_") else "MEDIUM",
            "raw": a.raw_text
        })
        
    for s in sms_alerts:
        combined.append({
            "id": f"sms_{s.id}",
            "source": "SMS",
            "bank": s.bank_name,
            "account": s.account_suffix,
            "amount": float(s.amount),
            "reference": s.utr_reference,
            "timestamp": s.transaction_timestamp.isoformat(),
            "confidence": "HIGH" if s.parsed_confidence >= 0.9 else "MEDIUM" if s.parsed_confidence >= 0.6 else "LOW",
            "payer": s.payer_name,
            "raw": s.raw_body
        })
        
    # Sort by timestamp desc
    combined.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return combined[:50]

if __name__ == "__main__":
    import uvicorn
    # Check for SSL
    cert_path = r"C:\Aradhana\SSL\cert.pem"
    key_path = r"C:\Aradhana\SSL\key.pem"
    
    if os.path.exists(cert_path) and os.path.exists(key_path):
        print(f"--- SSL Enabled: Starting Backend on HTTPS ---")
        uvicorn.run(
            "backend.review_api:app", 
            host="0.0.0.0", 
            port=8000, 
            ssl_keyfile=key_path, 
            ssl_certfile=cert_path,
            reload=True
        )
    else:
        print(f"--- SSL Disabled: cert/key not found. Starting Backend on HTTP ---")
        uvicorn.run(
            "backend.review_api:app", 
            host="0.0.0.0", 
            port=8000,
            reload=True
        )
