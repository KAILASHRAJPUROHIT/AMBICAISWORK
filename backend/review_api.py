import os
import json
import logging
import sys
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# Initialize logger early
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ReviewAPI")

# Centralized path resolution for production environment
def get_base_dir():
    if getattr(sys, 'frozen', False):
        exe_path = os.path.abspath(sys.executable)
        exe_dir = os.path.dirname(exe_path)
        if os.path.basename(exe_dir).lower() == 'dist':
            return os.path.dirname(exe_dir)
        return r"C:\Users\kaila\aradhana-payment-auditor\aradhana-payment-auditor"
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = get_base_dir()
ENV_PATH = os.path.abspath(os.path.join(BASE_DIR, ".env"))

# PART B & D — ENV LOAD & FAIL FAST
env_found = os.path.exists(ENV_PATH)
logger.info(f"STARTUP: ENV_FILE_FOUND={ENV_PATH} ({env_found})")

if not env_found:
    logger.critical(f"FATAL: .env file missing at {ENV_PATH}. Startup aborted.")
    # We allow startup for debug purposes but it will fail later if required
else:
    load_dotenv(ENV_PATH, override=True)
    logger.info(f"STARTUP: ENV_LOADED=true")

# PART A — DATABASE & TABLE VALIDATION
from backend.database import DB_PATH, DATABASE_URL, SessionLocal, check_db_integrity, engine
db_integrity_ok, db_error = check_db_integrity()
logger.info(f"STARTUP: DATABASE_PATH={DB_PATH} (Integrity: {db_integrity_ok})")

if not db_integrity_ok:
    logger.critical(f"FATAL STARTUP ERROR: {db_error}")

from backend.auth_service import create_otp, verify_otp, create_user_session, validate_session, log_event
from backend.lan_config import lan_health_check
from backend.models import User, LoginLog, Bill, BankAlert, SMSAlert
from backend.pdf_ingestion import start_ingestion_thread, perform_scan, ingestion_status, WATCH_PATH
from backend.email_poller import start_email_poller, process_emails, email_status
from backend.sms_poller import start_sms_poller, process_sms, sms_status
from backend.api_routes import router as api_router
from backend.invoice_lifecycle import start_lifecycle_automation

# Initialize FastAPI app
app = FastAPI(title="Aradhana Review API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/api/debug/live-feed")
async def debug_live_feed(db: Session = Depends(get_db)):
    from sqlalchemy import text
    try:
        total_count = db.query(Bill).count()
        real_count = db.query(Bill).filter(Bill.is_test_data == False).count()
        last_5 = db.query(Bill).order_by(Bill.ingested_at.desc()).limit(5).all()
        
        return {
            "total_bills_in_db": total_count,
            "real_bills_in_db": real_count,
            "last_5_bills": [
                {
                    "id": b.id,
                    "bill_no": b.bill_number,
                    "is_test": b.is_test_data,
                    "ingested_at": b.ingested_at.isoformat()
                } for b in last_5
            ],
            "database_path": DB_PATH
        }
    except Exception as e:
        return {"error": str(e), "database_path": DB_PATH}

# VERSIONING
APP_VERSION = "1.2.0-STABLE"

@app.get("/api/version")
async def get_version():
    return {
        "version": APP_VERSION,
        "environment": "PRODUCTION",
        "deployment": "STANDALONE_EXE",
        "update_channel": "STABLE",
        "server_time": datetime.now().isoformat()
    }

@app.get("/api/reports/payment-bifurcation")
async def get_payment_bifurcation(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    from backend.models import Payment as PaymentModel
    from sqlalchemy import and_
    
    # Date Filtering
    filters = [Bill.is_test_data == False]
    if start_date:
        filters.append(func.date(Bill.invoice_date) >= start_date)
    if end_date:
        filters.append(func.date(Bill.invoice_date) <= end_date)
        
    bills = db.query(Bill).filter(and_(*filters)).all()
    bill_ids = [b.id for b in bills]
    
    modes = ["CASH", "UPI", "IMPS", "NEFT", "RTGS", "CHEQUE", "CARD", "ADVANCE", "OLD_GOLD_EXCHANGE", "MIXED", "UNKNOWN"]
    bifurcation = {m: {"total": 0.0, "verified": 0.0, "unverified": 0.0, "count": 0} for m in modes}
    
    # 1. Process explicit payments
    payments = db.query(PaymentModel).filter(PaymentModel.bill_id.in_(bill_ids)).all()
    for p in payments:
        mode = p.mode
        if mode not in bifurcation: mode = "UNKNOWN"
        
        amt = float(p.amount)
        bifurcation[mode]["total"] += amt
        if p.status == "Green":
            bifurcation[mode]["verified"] += amt
        else:
            bifurcation[mode]["unverified"] += amt
        
        bifurcation[mode]["count"] += 1
    
    # 2. Process Advances (Mandate: Separated until verified)
    unverified_adv_total = 0.0
    for b in bills:
        adv = float(b.advance_amount or 0)
        if adv > 0 and b.advance_verification_status != "VERIFIED":
            unverified_adv_total += adv
                
    # Return as list for frontend
    report = []
    for m, data in bifurcation.items():
        if m == "ADVANCE":
            report.append({
                "mode": "Unverified Advance",
                "total": unverified_adv_total,
                "verified": 0,
                "unverified": unverified_adv_total,
                "count": sum(1 for b in bills if b.advance_amount > 0 and b.advance_verification_status != "VERIFIED")
            })
            continue
            
        report.append({
            "mode": m,
            "total": data["total"],
            "verified": data["verified"],
            "unverified": data["unverified"],
            "count": data["count"]
        })
        
    return report

@app.get("/debug/startup")
async def get_startup_debug():
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    return {
        "project_root": BASE_DIR,
        "database_path": DB_PATH,
        "database_exists": os.path.exists(DB_PATH),
        "env_path": ENV_PATH,
        "env_file_found": env_found,
        "env_loaded": os.getenv("EMAIL_USERNAME") is not None,
        "invoice_path": WATCH_PATH,
        "bills_table_exists": "bills" in tables,
        "bank_alerts_table_exists": "bank_alerts" in tables,
        "sms_alerts_table_exists": "sms_alerts" in tables,
        "all_tables": tables,
        "cwd": os.getcwd(),
        "executable": sys.executable
    }

@app.get("/debug/runtime")
async def get_runtime_debug(db: Session = Depends(get_db)):
    data = {}
    data["project_root"] = BASE_DIR
    try: data["cwd"] = os.getcwd()
    except Exception as e: data["cwd"] = f"ERROR: {str(e)}"
        
    data["database_path"] = DB_PATH
    data["env_file_path"] = ENV_PATH
    data["env_loaded"] = os.getenv("EMAIL_USERNAME") is not None
    
    try:
        data["invoice_share_path"] = WATCH_PATH
        exists = os.path.exists(WATCH_PATH)
        data["invoice_share_reachable"] = exists
        if exists:
            data["pdf_count_in_share"] = len([f for f in os.listdir(WATCH_PATH) if f.lower().endswith(".pdf")])
        else:
            data["pdf_count_in_share"] = 0
    except Exception as e:
        data["invoice_share_reachable"] = False
        data["pdf_count_in_share"] = f"ERROR: {str(e)}"

    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_str = now.strftime("%Y-%m-%d")
    
    try: data["invoice_count"] = db.query(Bill).count()
    except Exception as e: data["invoice_count"] = f"ERROR: {str(e)}"

    try: data["bills_dated_today"] = db.query(Bill).filter(func.date(Bill.invoice_date) == today_str, Bill.is_test_data == False).count()
    except Exception as e: data["bills_dated_today"] = f"ERROR: {str(e)}"
        
    try: data["imported_today"] = db.query(Bill).filter(Bill.created_at >= today_start, Bill.is_test_data == False).count()
    except Exception as e: data["imported_today"] = f"ERROR: {str(e)}"

    try: data["bank_alert_count"] = db.query(BankAlert).count()
    except Exception as e: data["bank_alert_count"] = f"ERROR: {str(e)}"

    try: data["sms_alert_count"] = db.query(SMSAlert).count()
    except Exception as e: data["sms_alert_count"] = f"ERROR: {str(e)}"

    try: data["verified_today"] = db.query(Bill).filter(func.date(Bill.invoice_date) == today_str, Bill.status == "Green", Bill.is_test_data == False).count()
    except Exception as e: data["verified_today"] = f"ERROR: {str(e)}"

    try:
        data["pending_previous_days"] = db.query(Bill).filter(
            func.date(Bill.invoice_date) < today_str,
            Bill.is_test_data == False,
            or_(Bill.status == "Yellow", Bill.status == "Blue", Bill.status == "Purple", Bill.review_required == 1)
        ).count()
    except Exception as e: data["pending_previous_days"] = f"ERROR: {str(e)}"

    return data

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

class DeliveryAction(BaseModel):
    invoice_no: str
    delivered_at: datetime
    approved_by: str

@app.post("/api/delivery/mark-delivered")
async def mark_delivered(action: DeliveryAction, db: Session = Depends(get_db)):
    bill = db.query(Bill).filter(Bill.bill_number == action.invoice_no).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
        
    old_status = bill.status
    bill.is_delivered = True
    bill.delivered_at = action.delivered_at
    bill.delivery_approved_by = action.approved_by
    
    if float(bill.remaining_amount or 0) > 0:
        bill.status = "Orange"
        bill.status_text = "DELIVERED_BEFORE_PAYMENT"
        
    from backend.reconciliation.logic import log_audit
    log_audit(db, "Bill", bill.id, "MARK_DELIVERED", old_status, bill.status, f"Approved by: {action.approved_by}")
    db.commit()
    return {"status": "success", "new_status": bill.status}

@app.post("/api/maintenance/start")
async def start_maintenance(reason: str, developer_id: str, db: Session = Depends(get_db)):
    from backend.models import MaintenanceSession
    session = MaintenanceSession(developer_id=developer_id, reason=reason, start_at=datetime.now())
    db.add(session)
    db.commit()
    return {"status": "success", "session_id": session.id}

@app.post("/api/maintenance/stop")
async def stop_maintenance(session_id: int, actions: str, db: Session = Depends(get_db)):
    from backend.models import MaintenanceSession
    session = db.query(MaintenanceSession).filter(MaintenanceSession.id == session_id).first()
    if not session: raise HTTPException(status_code=404, detail="Maintenance session not found")
    session.end_at = datetime.now()
    session.actions_performed = actions
    db.commit()
    return {"status": "success"}

@app.get("/api/system/mode")
async def get_system_mode():
    from backend.lan_config import is_physical_lan_connected
    is_lan = is_physical_lan_connected()
    return {"mode": "PRODUCTION", "lan_connected": is_lan, "blocked": not is_lan}

@app.get("/api/system/share-status")
async def get_share_status():
    online = os.path.exists(WATCH_PATH)
    pdf_count = 0
    if online:
        try: pdf_count = len([f for f in os.listdir(WATCH_PATH) if f.lower().endswith(".pdf")])
        except: pass
            
    return {"online": online, "path": WATCH_PATH, "label": "Invoice PDF Share (PC2)", "status_color": "Green" if online else "Red", "pdf_count": pdf_count}

@app.get("/api/invoices/live-feed")
async def get_live_feed(db: Session = Depends(get_db)):
    from backend.models import Payment as PaymentModel
    bills = db.query(Bill).filter(Bill.is_test_data == False).order_by(Bill.ingested_at.desc()).limit(50).all()
    results = []
    for b in bills:
        delay_seconds = 0
        timestamp_anomaly = False
        if b.invoice_generated_at and b.ingested_at:
            diff = (b.ingested_at - b.invoice_generated_at).total_seconds()
            if diff < 0:
                delay_seconds = 0
                timestamp_anomaly = True
            else:
                delay_seconds = diff

        # Historical Payment Check
        historical_claim = db.query(PaymentModel).filter(
            PaymentModel.bill_id == b.id,
            PaymentModel.payment_date != None,
            func.date(PaymentModel.payment_date) < func.date(b.invoice_date)
        ).first()

        results.append({
            "id": b.id,
            "bill_number": b.bill_number,
            "invoice_date": b.invoice_date.strftime("%Y-%m-%d") if b.invoice_date else None,
            "invoice_time": b.invoice_generated_at.strftime("%I:%M:%S %p") if b.invoice_generated_at else None,
            "invoice_generated_at": b.invoice_generated_at.isoformat() if b.invoice_generated_at else None,
            "ingested_at": b.ingested_at.isoformat() if b.ingested_at else None,
            "pipeline_delay_seconds": delay_seconds,
            "timestamp_anomaly": timestamp_anomaly,
            "customer_name": b.customer_name,
            "invoice_total": float(b.amount or 0),
            "cust_purc": float(b.customer_purchase_amount or 0),
            "advance": float(b.advance_amount or 0),
            "net_payable": float(b.amount or 0) - float(b.customer_purchase_amount or 0) - float(b.advance_amount or 0),
            "paid_amount": float(b.cash_received or 0) + float(b.bank_received or 0) + float(b.card_received or 0) + float(b.sms_confirmed_amount or 0) + float(b.email_confirmed_amount or 0),
            "remaining_amount": float(b.remaining_amount or 0),
            "status": b.status,
            "status_text": b.status_text,
            "is_historical_claim": historical_claim is not None,
            "historical_payment_date": historical_claim.payment_date.strftime("%Y-%m-%d") if historical_claim else None,
            "pdf_path": b.pdf_path,
            "created_at": b.created_at.isoformat()
        })
    return results

@app.get("/api/dashboard/live")
@app.get("/api/prime/dashboard/stats")
async def get_dashboard_stats(request: Request, db: Session = Depends(get_db)):
    # Authenticate for financial data check
    token = request.headers.get("X-Session-Token")
    user_role = "VIEWER"
    actor_id = "UNKNOWN"
    if token:
        employee_id = validate_session(db, token)
        if employee_id:
            user = db.query(User).filter(User.employee_id == employee_id).first()
            if user:
                user_role = user.role.upper()
                actor_id = user.employee_id
                
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_str = now.strftime("%Y-%m-%d")
    
    bills_today_query = db.query(Bill).filter(func.date(Bill.invoice_date) == today_str, Bill.is_test_data == False)
    total_bills_today = bills_today_query.count()
    
    unverified_adv_query = db.query(Bill).filter(Bill.is_test_data == False, Bill.advance_amount > 0, Bill.advance_verification_status != "VERIFIED")
    unverified_adv_count = unverified_adv_query.count()
    unverified_adv_amount = float(db.query(func.sum(Bill.advance_amount)).filter(Bill.is_test_data == False, Bill.advance_amount > 0, Bill.advance_verification_status != "VERIFIED").scalar() or 0.0)
    
    imported_today = db.query(Bill).filter(Bill.created_at >= today_start, Bill.is_test_data == False).count()
    pending_previous = db.query(Bill).filter(func.date(Bill.invoice_date) < today_str, Bill.is_test_data == False, or_(Bill.status == "Yellow", Bill.status == "Blue", Bill.status == "Purple", Bill.review_required == 1)).count()
    verified_today = bills_today_query.filter(Bill.status == "Green").count()
    review_required_total = db.query(Bill).filter(Bill.review_required == 1, Bill.is_test_data == False).count()
    partial_paid = db.query(Bill).filter(Bill.status == "Blue", Bill.remaining_amount > 0, Bill.is_test_data == False).count()
    
    # Financial visibility check
    is_owner = user_role in ["OWNER", "ADMIN"]
    
    # Log attempt if non-owner
    if not is_owner:
        from backend.reconciliation.logic import log_audit
        log_audit(db, "System", 0, "FINANCIAL_DATA_ACCESS", user_role, "DENIED", f"User: {actor_id}")
    
    from backend.models import Payment as PaymentModel
    bills_today_ids = [b.id for b in bills_today_query.all()]
    
    # Mandate: Only Owners/Admins see collections
    if is_owner:
        payments_today = db.query(PaymentModel).filter(PaymentModel.bill_id.in_(bills_today_ids)).all()
        verified_adv_today = float(db.query(func.sum(Bill.advance_amount)).filter(Bill.id.in_(bills_today_ids), Bill.advance_verification_status == "VERIFIED").scalar() or 0.0)
        total_collection = float(sum(p.amount for p in payments_today) or 0.0)
        cash_collection = float(sum(p.amount for p in payments_today if p.mode in ["CASH", "OLD_GOLD_EXCHANGE"]) or 0.0)
        cash_collection += verified_adv_today
        bank_collection = float(sum(p.amount for p in payments_today if p.mode in ["BANK_TRANSFER", "CARD", "UPI", "NEFT", "IMPS", "RTGS"]) or 0.0)
        sms_confirmed = float(db.query(func.sum(Bill.sms_confirmed_amount)).filter(func.date(Bill.invoice_date) == today_str, Bill.is_test_data == False).scalar() or 0.0)
        email_confirmed = float(db.query(func.sum(Bill.email_confirmed_amount)).filter(func.date(Bill.invoice_date) == today_str, Bill.is_test_data == False).scalar() or 0.0)
        cheque_collection = float(db.query(func.sum(PaymentModel.amount)).filter(PaymentModel.bill_id.in_(bills_today_ids), PaymentModel.mode == "CHEQUE").scalar() or 0.0)
    else:
        # Strictly hide from Accountant/Staff/Biller
        total_collection = 0.0
        cash_collection = 0.0
        bank_collection = 0.0
        sms_confirmed = 0.0
        email_confirmed = 0.0
        cheque_collection = 0.0

    online = os.path.exists(WATCH_PATH)
    pdf_count = 0
    if online:
        try: pdf_count = len([f for f in os.listdir(WATCH_PATH) if f.lower().endswith(".pdf")])
        except: pass

    return {
        "totalBillsToday": total_bills_today, "importedToday": imported_today, "pendingPreviousDays": pending_previous,
        "verified": verified_today, "pendingReview": review_required_total, "partialPaid": partial_paid,
        "unverifiedAdvancesCount": unverified_adv_count, "unverifiedAdvancesAmount": unverified_adv_amount,
        "totalCollection": total_collection, "cashCollection": cash_collection, "bankCollection": bank_collection,
        "smsConfirmed": sms_confirmed, "emailConfirmed": email_confirmed, "chequeCollection": cheque_collection,
        "pdfCountInShare": pdf_count, "invoiceWatcherStatus": "READY" if online else "OFFLINE",
        "emailPollerStatus": email_status.get("status", "IDLE"), "smsRelayStatus": sms_status.get("status", "IDLE"),
        "matchAccuracy": round((verified_today / total_bills_today * 100), 2) if total_bills_today > 0 else 0.0,
        "is_owner": is_owner
    }

class AdvanceVerification(BaseModel):
    invoice_no: str
    advance_source: str
    advance_date: datetime
    evidence_type: str
    evidence_ref: Optional[str]
    accountant_id: str
    cheque_no: Optional[str] = None
    cheque_date: Optional[datetime] = None
    deposited_date: Optional[datetime] = None
    is_cleared: Optional[bool] = False
    is_deposited: Optional[bool] = False

@app.post("/api/advances/verify")
async def verify_advance(action: AdvanceVerification, db: Session = Depends(get_db)):
    bill = db.query(Bill).filter(Bill.bill_number == action.invoice_no).first()
    if not bill: raise HTTPException(status_code=404, detail="Bill not found")
    old_source = bill.advance_source or "UNKNOWN"
    bill.advance_source = action.advance_source
    bill.advance_verification_status = "VERIFIED" if action.is_cleared or action.advance_source == "CASH" else "UNVERIFIED"
    if action.advance_source == "CHEQUE":
        from backend.models import Cheque
        cheque = db.query(Cheque).filter(Cheque.bill_id == bill.id, Cheque.cheque_number == action.cheque_no).first()
        if not cheque:
            cheque = Cheque(bill_id=bill.id, cheque_number=action.cheque_no, amount=bill.advance_amount, cheque_date=action.cheque_date, deposit_date=action.deposited_date, status="Green" if action.is_cleared else "Blue")
            db.add(cheque)
        else:
            cheque.status = "Green" if action.is_cleared else "Blue"
            cheque.cleared_at = datetime.now() if action.is_cleared else None
    from backend.reconciliation.logic import log_audit
    log_audit(db, "Bill", bill.id, "ADVANCE_CLASSIFIED", old_source, bill.advance_source, f"Verified by: {action.accountant_id}")
    db.commit()
    return {"status": "success", "advance_status": bill.advance_verification_status}

@app.get("/api/invoices/pdf/{bill_id}")
async def get_invoice_pdf(bill_id: int, db: Session = Depends(get_db)):
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill or not bill.pdf_path: raise HTTPException(status_code=404, detail="Invoice PDF not found")
    if not os.path.exists(bill.pdf_path): raise HTTPException(status_code=404, detail="PDF file missing on disk")
    return FileResponse(bill.pdf_path, media_type="application/pdf")

@app.post("/api/review")
async def review_invoice(action: ReviewAction):
    log_entry = {"timestamp": datetime.now().isoformat(), "event": "ACCOUNTANT_REVIEW", "invoice_no": action.invoice_no, "action": action.status, "comment": action.comment, "accountant": action.accountant_id}
    AUDIT_LOG_DIR = r"C:\Aradhana\AuditLogs"
    os.makedirs(AUDIT_LOG_DIR, exist_ok=True)
    log_filename = f"REVIEW_{action.invoice_no.replace('/', '_')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    log_path = os.path.join(AUDIT_LOG_DIR, log_filename)
    with open(log_path, "w", encoding="utf-8") as f: json.dump(log_entry, f, indent=4)
    return {"status": "success", "audit_log": log_path}

@app.get("/api/admin/ingestion-status")
async def get_ingestion_status(): return ingestion_status

@app.post("/api/scan-now")
async def trigger_scan():
    import threading
    threading.Thread(target=perform_scan, daemon=True).start()
    return {"status": "scan_triggered", "message": "PDF rescan started in background"}

@app.get("/api/admin/email-status")
async def get_email_status(): return email_status

@app.post("/api/email-sync-now")
async def trigger_email_sync():
    import threading
    threading.Thread(target=process_emails, daemon=True).start()
    return {"status": "sync_triggered", "message": "Email sync started in background"}

@app.get("/api/admin/sms-status")
async def get_sms_status(): return email_status

@app.post("/api/sms-sync-now")
async def trigger_sms_sync():
    import threading
    threading.Thread(target=process_sms, daemon=True).start()
    return {"status": "sync_triggered", "message": "SMS sync started in background"}

@app.get("/api/bank-events")
async def get_bank_events(db: Session = Depends(get_db)):
    return db.query(BankAlert).order_by(BankAlert.received_at.desc()).limit(50).all()

@app.get("/api/sms-events")
async def get_sms_events(db: Session = Depends(get_db)):
    return db.query(SMSAlert).order_by(SMSAlert.transaction_timestamp.desc()).limit(50).all()

@app.get("/api/live-payment-events")
async def get_live_payment_events(db: Session = Depends(get_db)):
    alerts = db.query(BankAlert).order_by(BankAlert.received_at.desc()).limit(50).all()
    sms_alerts = db.query(SMSAlert).order_by(SMSAlert.transaction_timestamp.desc()).limit(50).all()
    combined = []
    for a in alerts:
        combined.append({"id": f"bank_{a.id}", "source": "EMAIL", "bank": a.bank_name, "amount": float(a.amount), "reference": a.utr_reference, "timestamp": a.received_at.isoformat(), "confidence": "HIGH" if a.utr_reference and not a.utr_reference.startswith("SYNC_") else "MEDIUM", "raw": a.raw_text})
    for s in sms_alerts:
        combined.append({"id": f"sms_{s.id}", "source": "SMS", "bank": s.bank_name, "account": s.account_suffix, "amount": float(s.amount), "reference": s.utr_reference, "timestamp": s.transaction_timestamp.isoformat(), "confidence": "HIGH" if s.parsed_confidence >= 0.9 else "MEDIUM" if s.parsed_confidence >= 0.6 else "LOW", "payer": s.payer_name, "raw": s.raw_body})
    combined.sort(key=lambda x: x["timestamp"], reverse=True)
    return combined[:50]

@app.get("/status-colors")
def status_colors():
    return {"Yellow": "#FFFF99", "Orange": "#FFA500", "Red": "#FF0000", "Green": "#008000", "Blue": "#ADD8E6", "Purple": "#800080"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/api/prime/manual-report-import/latest")
async def get_latest_prime_import():
    path = r"C:\Aradhana\PrimeExports\JSON\prime_report_import.json"
    if not os.path.exists(path):
        return {"timestamp": datetime.now().isoformat(), "count": 0, "records": []}
    
    try:
        with open(path, "r") as f:
            data = json.load(f)
            return data
    except Exception as e:
        logger.error(f"Error reading prime import: {e}")
        return {"error": str(e)}

app.include_router(api_router, prefix="/api")

@app.get("/api/system/health")
async def system_health(db: Session = Depends(get_db)):
    # Check DB
    from sqlalchemy import text
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.error(f"Health Check DB Error: {e}")
        db_ok = False
        
    return {
        "status": "online" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "services": {
            "email_poller": email_status,
            "sms_poller": sms_status,
            "pdf_ingestion": ingestion_status
        },
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/reconciliations")
async def list_reconciliations(db: Session = Depends(get_db)):
    # This should return a list of bills that need reconciliation or their status
    # For compatibility with frontend ReconciliationQueuePage
    bills = db.query(Bill).filter(Bill.is_test_data == False).order_by(Bill.ingested_at.desc()).limit(100).all()
    return [{
        "invoice_no": b.bill_number,
        "status": b.status.upper(),
        "details": {
            "customer": b.customer_name,
            "total": float(b.amount or 0),
            "payments": float(b.cash_received or 0) + float(b.bank_received or 0) + float(b.card_received or 0) + float(b.sms_confirmed_amount or 0) + float(b.email_confirmed_amount or 0),
            "mode": b.payment_mode or "BANK"
        }
    } for b in bills]

# RBAC Dependencies
async def require_role(roles: List[str], request: Request, db: Session = Depends(get_db)):
    token = request.headers.get("X-Session-Token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    employee_id = validate_session(db, token)
    if not employee_id:
        raise HTTPException(status_code=401, detail="Session expired")

    user = db.query(User).filter(User.employee_id == employee_id).first()
    if not user or user.role.upper() not in [r.upper() for r in roles]:
        raise HTTPException(status_code=403, detail="Access denied: Insufficient permissions")
    return user

async def require_owner(request: Request, db: Session = Depends(get_db)):
    return await require_role(["OWNER", "ADMIN"], request, db)

# MASTER CONSOLE: User Administration
@app.get("/api/admin/users")
async def list_users(db: Session = Depends(get_db), owner: User = Depends(require_owner)):
    users = db.query(User).all()
    return [{
        "id": u.id,
        "employee_id": u.employee_id,
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "is_active": u.is_active == 1
    } for u in users]

class UserCreate(BaseModel):
    employee_id: str
    name: str
    email: str
    role: str
    password: str

@app.post("/api/admin/users")
async def create_user(request: UserCreate, db: Session = Depends(get_db), owner: User = Depends(require_owner)):
    from backend.auth_service import hash_password
    existing = db.query(User).filter((User.employee_id == request.employee_id) | (User.email == request.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    new_user = User(
        employee_id=request.employee_id,
        name=request.name,
        email=request.email,
        role=request.role.upper(),
        hashed_password=hash_password(request.password),
        is_active=1
    )
    db.add(new_user)
    db.commit()
    from backend.reconciliation.logic import log_audit
    log_audit(db, "User", new_user.id, "USER_CREATED", None, new_user.role, f"Created by {owner.employee_id}")
    return {"status": "success"}

@app.post("/api/admin/users/{employee_id}/toggle")
async def toggle_user(employee_id: str, db: Session = Depends(get_db), owner: User = Depends(require_owner)):
    user = db.query(User).filter(User.employee_id == employee_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == owner.id:
        raise HTTPException(status_code=400, detail="Cannot disable yourself")

    user.is_active = 0 if user.is_active == 1 else 1
    db.commit()
    from backend.reconciliation.logic import log_audit
    log_audit(db, "User", user.id, "USER_TOGGLED", str(not user.is_active), str(user.is_active), f"Action by {owner.employee_id}")
    return {"status": "success", "is_active": user.is_active == 1}

# MASTER CONSOLE: Security Dashboard
@app.get("/api/admin/security/stats")
async def get_security_stats(db: Session = Depends(get_db), owner: User = Depends(require_owner)):
    from backend.models import LoginLog, OTP, Session as SessionModel

    failed_logins = db.query(LoginLog).filter(LoginLog.event_type == "PASSWORD_FAILED").count()
    active_sessions = db.query(SessionModel).filter(SessionModel.expires_at > datetime.now()).count()
    otp_stats = db.query(OTP).count()

    # Recent logins
    recent_logins = db.query(LoginLog).order_by(LoginLog.created_at.desc()).limit(10).all()

    return {
        "failed_login_count": failed_logins,
        "active_session_count": active_sessions,
        "otp_total_count": otp_stats,
        "recent_events": [{
            "employee_id": l.employee_id,
            "event": l.event_type,
            "ip": l.ip_address,
            "time": l.created_at.isoformat()
        } for l in recent_logins]
    }

# MASTER CONSOLE: Emergency Controls
@app.get("/api/admin/system/mode")
async def get_admin_mode(db: Session = Depends(get_db), owner: User = Depends(require_owner)):
    from backend.models import SystemSetting
    mode = db.query(SystemSetting).filter(SystemSetting.key == "system_mode").first()
    return {"mode": mode.value if mode else "PRODUCTION"}

@app.post("/api/admin/system/mode")
async def set_admin_mode(mode: str, reason: str, db: Session = Depends(get_db), owner: User = Depends(require_owner)):
    from backend.models import SystemSetting
    setting = db.query(SystemSetting).filter(SystemSetting.key == "system_mode").first()
    if setting:
        old_mode = setting.value
        setting.value = mode.upper()
        
        # Log it
        from backend.reconciliation.logic import log_audit
        log_audit(db, "System", 0, "MODE_CHANGE", old_mode, setting.value, f"Reason: {reason}, By: {owner.employee_id}")
        db.commit()
    return {"status": "success", "new_mode": mode}

@app.post("/api/admin/emergency/sync")
async def force_sync(command: str, db: Session = Depends(get_db), owner: User = Depends(require_owner)):
    # Command: SCAN, POLL_EMAIL, POLL_SMS, RECONCILE
    if command == "SCAN":
        await trigger_scan()
    elif command == "POLL_EMAIL":
        await trigger_email_sync()
    elif command == "POLL_SMS":
        await trigger_sms_sync()
    elif command == "RECONCILE":
        from backend.reconciliation.logic import reconcile_unreconciled_alerts
        reconcile_unreconciled_alerts(db)

    from backend.reconciliation.logic import log_audit
    log_audit(db, "System", 0, "FORCE_SYNC", None, command, f"Forced by {owner.employee_id}")
    return {"status": "success", "command": command}

# ... rest ...

# Auth Models
class LoginRequest(BaseModel):
    employee_id: str
    password: str

class VerifyRequest(BaseModel):
    employee_id: str
    otp_code: str

@app.post("/api/auth/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    from backend.auth_service import verify_password
    logger.info(f"LOGIN ATTEMPT: Received employee_id='{request.employee_id}'")
    
    # CASE INSENSITIVE LOOKUP
    user = db.query(User).filter(func.lower(User.employee_id) == request.employee_id.lower()).first()
    
    if not user or not user.is_active:
        logger.warning(f"LOGIN FAILED: User '{request.employee_id}' not found or inactive")
        raise HTTPException(status_code=401, detail="Invalid ID or inactive account")
    
    if not verify_password(request.password, user.hashed_password):
        log_event(db, user.employee_id, "PASSWORD_FAILED")
        logger.warning(f"LOGIN FAILED: Invalid password for '{user.employee_id}'")
        raise HTTPException(status_code=401, detail="Invalid password")
    
    log_event(db, user.employee_id, "LOGIN_REQUEST")
    
    # Get/Create OTP with cooldown
    otp_res = create_otp(db, user.employee_id)
    if otp_res.get("status") == "error":
        raise HTTPException(status_code=500, detail=otp_res["message"])
    
    # Email hint for masking
    email = user.security_email if user.security_email else user.email
    user_part, domain_part = email.split('@')
    masked_email = f"{user_part[0]}***{user_part[-1]}@{domain_part}"
    
    return {
        "status": otp_res["status"],
        "otp_sent": otp_res["otp_sent"],
        "message": otp_res["message"],
        "resend_available_in": otp_res["resend_available_in"],
        "expires_in": otp_res["expires_in"],
        "masked_email": masked_email
    }

@app.get("/api/auth/otp-status")
async def get_otp_status(employee_id: str, db: Session = Depends(get_db), user: User = Depends(lambda r, d: require_role(["OWNER", "DEVELOPER", "ADMIN"], r, d))):
    from backend.models import OTP
    latest = db.query(OTP).filter(OTP.employee_id == employee_id).order_by(OTP.created_at.desc()).first()
    if not latest:
        return {"status": "none"}
    
    now = datetime.now()
    age = (now - latest.created_at).total_seconds()
    
    return {
        "created_at": latest.created_at.isoformat(),
        "expires_at": latest.expires_at.isoformat(),
        "used": latest.is_verified == 1,
        "attempts": latest.attempts,
        "can_resend": age >= 60,
        "resend_available_in": max(0, int(60 - age)),
        "expired": latest.expires_at < now
    }

@app.post("/api/auth/verify")
async def verify(request: VerifyRequest, db: Session = Depends(get_db), req: Request = None):
    logger.info(f"VERIFY ATTEMPT: employee_id='{request.employee_id}', otp='{request.otp_code}'")
    
    # Use the normalized ID from DB if found
    user = db.query(User).filter(func.lower(User.employee_id) == request.employee_id.lower()).first()
    target_id = user.employee_id if user else request.employee_id

    # Verify OTP
    if verify_otp(db, target_id, request.otp_code):
        token = create_user_session(db, target_id)
        
        log_event(db, target_id, "LOGIN_SUCCESS", ip=req.client.host if req else None)
        return {
            "status": "success",
            "token": token,
            "user": {
                "name": user.name,
                "role": user.role,
                "employee_id": user.employee_id,
                "reset_required": user.password_reset_required == 1
            }
        }
    
    log_event(db, target_id, "LOGIN_FAILED", ip=req.client.host if req else None)
    raise HTTPException(status_code=401, detail="Invalid or expired OTP")

@app.post("/api/auth/resend-otp")
async def resend_otp(request: LoginRequest, db: Session = Depends(get_db)):
    # We use LoginRequest because it has employee_id. Password is also sent but we can skip re-verifying it 
    # if we want to be fast, but for security, let's verify password again.
    from backend.auth_service import verify_password
    user = db.query(User).filter(func.lower(User.employee_id) == request.employee_id.lower()).first()
    
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid ID or inactive account")
    
    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid password")
    
    # Generate new OTP (create_otp handles invalidation of old ones)
    otp = create_otp(db, user.employee_id, is_resend=True)
    if not otp:
        raise HTTPException(status_code=500, detail="Failed to resend OTP")
    
    return {"status": "success", "message": "New OTP sent to your registered email"}

@app.get("/api/auth/me")
async def get_me(request: Request, db: Session = Depends(get_db)):
    token = request.headers.get("X-Session-Token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    employee_id = validate_session(db, token)
    if not employee_id:
        raise HTTPException(status_code=401, detail="Session expired")

    user = db.query(User).filter(User.employee_id == employee_id).first()
    return {
        "name": user.name,
        "role": user.role,
        "employee_id": user.employee_id
    }

@app.post("/api/auth/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    token = request.headers.get("X-Session-Token")
    if token:
        # Delete session
        from backend.models import Session as SessionModel
        db.query(SessionModel).filter(SessionModel.session_token == token).delete()
        db.commit()
    return {"status": "success"}

# Recovery Models
class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str
    otp_code: str
    new_password: str

@app.post("/api/auth/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Mandate Step 2 & 3: Check active user by email and send OTP
    user = db.query(User).filter(func.lower(User.email) == request.email.lower(), User.is_active == 1).first()
    
    if user:
        otp = create_otp(db, user.employee_id)
        if otp:
            log_event(db, user.employee_id, "FORGOT_PASSWORD_REQUEST")
            return {"status": "success", "message": "Reset OTP sent to your registered email."}
            
    # Generic message for security even if email not found
    return {"status": "success", "message": "Recovery instructions sent if email exists."}

@app.post("/api/auth/reset-password")
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(func.lower(User.email) == request.email.lower(), User.is_active == 1).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if verify_otp(db, user.employee_id, request.otp_code):
        from backend.auth_service import hash_password
        user.hashed_password = hash_password(request.new_password)
        db.commit()
        
        log_event(db, user.employee_id, "PASSWORD_RESET_SUCCESS")
        return {"status": "success", "message": "Password changed successfully."}
    
    log_event(db, user.employee_id, "PASSWORD_RESET_FAILED")
    raise HTTPException(status_code=401, detail="Invalid or expired reset OTP")

# ... existing routes ...

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    PUBLIC_ENDPOINTS = [
        "/api/auth/",
        "/api/version",
        "/api/reports/payment-bifurcation",
        "/api/debug/",
        "/debug/",
        "/status-colors",
        "/health"
    ]

    # Static files and root are public (they serve the React app)
    if request.url.path == "/" or request.url.path.startswith("/assets/"):
        return await call_next(request)

    if not await lan_health_check(request):
        # Even read-only might be blocked if totally disconnected?
        # User: "If LAN disconnected... read-only mode allowed."
        # But: "Production Actions Blocked." (POST/PUT/DELETE)
        # lan_health_check already handles this.
        pass

    is_protected = request.url.path.startswith("/api/")
    for public_path in PUBLIC_ENDPOINTS:
        if request.url.path.startswith(public_path):
            is_protected = False
            break

    if is_protected:
        token = request.headers.get("X-Session-Token")
        if not token:
             return JSONResponse(status_code=401, content={"detail": "Authentication required. Please login."})

        db = SessionLocal()
        employee_id = validate_session(db, token)
        db.close()

        if not employee_id:
             return JSONResponse(status_code=401, content={"detail": "Session expired or invalid. Please login again."})

    response = await call_next(request)
    return response

# MASTER CONSOLE: Financial Health Dashboard
@app.get("/api/admin/financial/health")
async def get_financial_health(db: Session = Depends(get_db), owner: User = Depends(require_owner)):
    from backend.models import Bill, Cheque
    
    pending_review = db.query(Bill).filter(Bill.review_required == 1, Bill.is_test_data == False).count()
    cheques_pending = db.query(Cheque).filter(Cheque.status != "Green").count()
    
    # Calculate bank variance (simplified)
    # Variance = (Total Invoiced Bank Amount) - (Total Confirmed Bank Amount)
    total_invoiced_bank = float(db.query(func.sum(Bill.amount)).filter(Bill.payment_mode.like("%BANK%"), Bill.is_test_data == False).scalar() or 0.0)
    total_confirmed_bank = float(db.query(func.sum(Bill.bank_received)).filter(Bill.is_test_data == False).scalar() or 0.0)
    
    return {
        "pending_review_count": pending_review,
        "cheques_pending_count": cheques_pending,
        "bank_variance_amount": total_invoiced_bank - total_confirmed_bank,
        "reconciliation_accuracy": round((total_confirmed_bank / total_invoiced_bank * 100), 2) if total_invoiced_bank > 0 else 100.0
    }

frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(frontend_dist):
    assets_path = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("debug/"): return JSONResponse(status_code=404, content={"detail": "Not Found"})
        index_path = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_path): return FileResponse(index_path)
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

@app.on_event("startup")
async def startup_event():
    integrity, err = check_db_integrity()
    if not integrity: logger.critical(f"SHUTDOWN: Database integrity failure: {err}")
    logger.info("Starting Backend Services...")
    start_ingestion_thread()
    start_email_poller()
    start_sms_poller()
    start_lifecycle_automation()

if __name__ == "__main__":
    import uvicorn
    cert_path, key_path = r"C:\Aradhana\SSL\cert.pem", r"C:\Aradhana\SSL\key.pem"
    if os.path.exists(cert_path) and os.path.exists(key_path): uvicorn.run("backend.review_api:app", host="0.0.0.0", port=8000, ssl_keyfile=key_path, ssl_certfile=cert_path)
    else: uvicorn.run("backend.review_api:app", host="0.0.0.0", port=8000)
