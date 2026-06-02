import os
import json
import logging
import sys
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Initialize logger early
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ReviewAPI")

from backend.auth_service import create_otp, verify_otp, create_user_session, validate_session, log_event
from backend.lan_config import lan_health_check
from backend.database import SessionLocal, DATABASE_URL
from backend.models import User, LoginLog, Bill, BankAlert, SMSAlert
from backend.pdf_ingestion import start_ingestion_thread, perform_scan, ingestion_status, WATCH_PATH
from backend.email_poller import start_email_poller, process_emails, email_status
from backend.sms_poller import start_sms_poller, process_sms, sms_status
from backend.api_routes import router as api_router
from backend.invoice_lifecycle import start_lifecycle_automation

# Initialize FastAPI app
app = FastAPI(title="Aradhana Review API")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/debug/runtime")
async def get_runtime_debug(db: Session = Depends(get_db)):
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Calculate counts
    invoice_count = db.query(Bill).count()
    today_invoice_count = db.query(Bill).filter(Bill.created_at >= today_start).count()
    bank_alert_count = db.query(BankAlert).count()
    sms_alert_count = db.query(SMSAlert).count()
    verified_count = db.query(Bill).filter(Bill.status == "Green", Bill.created_at >= today_start).count()
    review_required_count = db.query(Bill).filter(Bill.review_required == 1, Bill.created_at >= today_start).count()
    
    # PDF check
    pdf_count = 0
    share_reachable = False
    if os.path.exists(WATCH_PATH):
        share_reachable = True
        try:
            pdf_count = len([f for f in os.listdir(WATCH_PATH) if f.lower().endswith(".pdf")])
        except Exception:
            pdf_count = -1

    return {
        "cwd": os.getcwd(),
        "executable": sys.executable,
        "database_path": DATABASE_URL,
        "database_exists": os.path.exists(DATABASE_URL.replace("sqlite:///", "")) if "sqlite" in DATABASE_URL else True,
        "env_loaded": os.getenv("IMAP_SERVER") is not None,
        "invoice_share_path": WATCH_PATH,
        "invoice_share_reachable": share_reachable,
        "pdf_count_in_share": pdf_count,
        "invoice_count": invoice_count,
        "today_invoice_count": today_invoice_count,
        "bank_alert_count": bank_alert_count,
        "sms_alert_count": sms_alert_count,
        "verified_count": verified_count,
        "review_required_count": review_required_count,
        "frontend_api_base": os.getenv("FRONTEND_API_BASE", "http://localhost:8000"),
        "backend_port": 8000,
        "sys_path": sys.path[:5]
    }

@app.get("/debug/routes")
async def get_routes():
    routes = []
    for route in app.routes:
        routes.append({
            "path": route.path,
            "name": route.name,
            "methods": list(route.methods) if hasattr(route, "methods") else []
        })
    return routes

# Models for API
class ReviewAction(BaseModel):
    invoice_no: str
    status: str
    comment: str
    accountant_id: str

@app.get("/api/system/share-status")
async def get_share_status():
    # User specified this path: \\PC2\AradhanaInvoicePDFs
    # In code it might be configured via WATCH_PATH
    online = os.path.exists(WATCH_PATH)
    pdf_count = 0
    if online:
        try:
            pdf_count = len([f for f in os.listdir(WATCH_PATH) if f.lower().endswith(".pdf")])
        except:
            pass
            
    return {
        "online": online,
        "path": WATCH_PATH,
        "label": "Invoice PDF Share (PC2)",
        "status_color": "Green" if online else "Red",
        "pdf_count": pdf_count
    }

@app.get("/api/invoices/live-feed")
async def get_live_feed(db: Session = Depends(get_db)):
    # Returns last 50 invoices for dashboard
    bills = db.query(Bill).order_by(Bill.created_at.desc()).limit(50).all()
    return bills

@app.get("/api/dashboard/live")
@app.get("/api/prime/dashboard/stats")
async def get_dashboard_stats(db: Session = Depends(get_db)):
    from backend.reconciliation.logic import is_store_open
    from sqlalchemy import or_, func
    
    # Use business date (today)
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_str = now.strftime("%Y-%m-%d")
    
    # 1. Base Stats
    # "Total Bills Today" = Invoices with invoice_date == today OR created_at >= today
    total_bills_query = db.query(Bill).filter(
        or_(
            Bill.created_at >= today_start,
            func.date(Bill.invoice_date) == today_str
        )
    )
    total_bills = total_bills_query.count()
    
    verified = total_bills_query.filter(Bill.status == "Green").count()
    
    # "Review Required" = ALL invoices that need review (even from yesterday)
    review_required = db.query(Bill).filter(Bill.review_required == 1).count()
    # "Review Required Today" = only those from today
    review_required_today = total_bills_query.filter(Bill.review_required == 1).count()
    
    partial_paid = db.query(Bill).filter(Bill.status == "Blue", Bill.remaining_amount > 0).count()
    
    # 2. Financial Metrics
    bills_today = total_bills_query.all()
    
    total_collection = float(sum(b.total_amount for b in bills_today) or 0.0)
    
    # Cash in Hand logic
    cash_confirmed = 0.0
    for b in bills_today:
        cash_confirmed += float(b.cash_received or 0.0)
            
    bank_confirmed = float(sum(b.bank_received for b in bills_today) or 0.0)
    sms_confirmed = float(sum(b.sms_confirmed_amount for b in bills_today) or 0.0)
    email_confirmed = float(sum(b.email_confirmed_amount for b in bills_today) or 0.0)
    cheque_pending = float(sum(b.total_amount for b in bills_today if "CHEQUE" in (b.payment_mode or "")) or 0.0)

    # Share status
    online = os.path.exists(WATCH_PATH)
    pdf_count = 0
    if online:
        try: pdf_count = len([f for f in os.listdir(WATCH_PATH) if f.lower().endswith(".pdf")])
        except: pass

    return {
        "totalBillsToday": total_bills,
        "verified": verified,
        "pendingReview": review_required,
        "pendingReviewToday": review_required_today,
        "partialPaid": partial_paid,
        "totalCollection": total_collection,
        "cashCollection": cash_confirmed,
        "bankCollection": bank_confirmed,
        "smsConfirmed": sms_confirmed,
        "emailConfirmed": email_confirmed,
        "chequeCollection": cheque_pending,
        "pdfCountInShare": pdf_count,
        "invoiceWatcherStatus": "READY" if online else "OFFLINE",
        "emailPollerStatus": email_status.get("status", "IDLE"),
        "smsRelayStatus": sms_status.get("status", "IDLE"),
        "matchAccuracy": round((verified / total_bills * 100), 2) if total_bills > 0 else 0.0
    }

@app.get("/api/invoices/pdf/{bill_id}")
async def get_invoice_pdf(bill_id: int, db: Session = Depends(get_db)):
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
    
    AUDIT_LOG_DIR = r"C:\Aradhana\AuditLogs"
    os.makedirs(AUDIT_LOG_DIR, exist_ok=True)
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
        
    combined.sort(key=lambda x: x["timestamp"], reverse=True)
    return combined[:50]

# Include API Router
app.include_router(api_router)

# Middleware for Security
@app.middleware("http")
async def security_middleware(request: Request, call_next):
    PUBLIC_ENDPOINTS = [
        "/api/auth",
        "/api/dashboard/live",
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
        "/api/invoices/pdf/",
        "/debug/runtime",
        "/debug/routes"
    ]
    
    if not await lan_health_check(request):
        pass
    
    is_protected = request.url.path.startswith("/api/")
    for public_path in PUBLIC_ENDPOINTS:
        if request.url.path.startswith(public_path):
            is_protected = False
            break
            
    if is_protected:
        token = request.headers.get("X-Session-Token")
        if not token:
             return JSONResponse(status_code=401, content={"detail": "Session token missing"})
        
        db = SessionLocal()
        employee_id = validate_session(db, token)
        db.close()
        
        if not employee_id:
             return JSONResponse(status_code=401, content={"detail": "Session expired or invalid"})
             
    response = await call_next(request)
    return response

# SPA Serving (MUST BE LAST)
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(frontend_dist):
    assets_path = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("debug/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
            
        index_path = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

@app.on_event("startup")
async def startup_event():
    logger.info("Starting Backend Services...")
    start_ingestion_thread()
    start_email_poller()
    start_sms_poller()
    start_lifecycle_automation()

if __name__ == "__main__":
    import uvicorn
    cert_path = r"C:\Aradhana\SSL\cert.pem"
    key_path = r"C:\Aradhana\SSL\key.pem"
    
    if os.path.exists(cert_path) and os.path.exists(key_path):
        logger.info("SSL Enabled: Starting Backend on HTTPS")
        uvicorn.run("backend.review_api:app", host="0.0.0.0", port=8000, ssl_keyfile=key_path, ssl_certfile=cert_path)
    else:
        logger.info("SSL Disabled: Starting Backend on HTTP")
        uvicorn.run("backend.review_api:app", host="0.0.0.0", port=8000)
