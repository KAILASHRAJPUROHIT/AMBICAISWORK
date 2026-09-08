import os
import json
import logging
import sys
import ipaddress
import re
import hashlib
import ctypes
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request as UrlRequest, urlopen
from uuid import uuid4
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse, PlainTextResponse
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
    load_dotenv(ENV_PATH, override=False)
    logger.info(f"STARTUP: ENV_LOADED=true")

# PART A — DATABASE & TABLE VALIDATION
from backend.database import DB_PATH, DATABASE_URL, DATABASE_LABEL, IS_SQLITE, SessionLocal, check_db_integrity, engine
db_integrity_ok, db_error = check_db_integrity()
logger.info(f"STARTUP: DATABASE={DATABASE_LABEL} (Integrity: {db_integrity_ok})")

if not db_integrity_ok:
    logger.critical(f"FATAL STARTUP ERROR: {db_error}")

from backend.auth_service import create_otp, verify_otp, create_user_session, validate_session, log_event, hash_password
from backend.lan_config import lan_health_check
from backend.models import User, LoginLog, Bill, Payment, BankAlert, SMSAlert, SystemSetting, AuditLog
from backend.pdf_ingestion import (
    start_ingestion_thread,
    perform_scan,
    ingestion_status,
    WATCH_PATH,
    SOURCE_SHARE_PATH,
    LOCAL_INBOX_PATH,
)
from backend.email_poller import start_email_poller, process_emails, email_status
from backend.sms_poller import start_sms_poller, process_sms, sms_status
from backend.kyc_ocr_warmup_poller import start_kyc_ocr_warmup_poller, warmup_poller_status
from backend.kyc_ocr_consumer import start_kyc_ocr_consumer, kyc_consumer_status
from backend.reconciliation.logic import calculate_payment_proof_status
from backend.sms_parser import detect_credit_or_debit, extract_account_display, extract_counterparty, extract_payment_mode, parse_bank_sms
from backend.api_routes import router as api_router
from backend.invoice_lifecycle import start_lifecycle_automation

# Initialize FastAPI app
app = FastAPI(title="Aradhana Review API")
SERVICE_START_TIME = datetime.now()
QR_DOCUMENT_SERVER_URL = os.environ.get("QR_DOCUMENT_SERVER_URL", "https://print.aradhanajewellers.com").rstrip("/")


def _windows_credential(target: str) -> str:
    """Read a Generic Credential without placing its secret in config or logs."""
    if os.name != "nt":
        return ""
    class Credential(ctypes.Structure):
        _fields_ = [("Flags", ctypes.c_uint32), ("Type", ctypes.c_uint32), ("TargetName", ctypes.c_void_p),
                    ("Comment", ctypes.c_void_p), ("LastWritten", ctypes.c_byte * 8),
                    ("CredentialBlobSize", ctypes.c_uint32), ("CredentialBlob", ctypes.c_void_p),
                    ("Persist", ctypes.c_uint32), ("AttributeCount", ctypes.c_uint32), ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", ctypes.c_void_p), ("UserName", ctypes.c_void_p)]
    pointer = ctypes.c_void_p()
    try:
        if not ctypes.windll.advapi32.CredReadW(target, 1, 0, ctypes.byref(pointer)):
            return ""
        credential = ctypes.cast(pointer, ctypes.POINTER(Credential)).contents
        if not credential.CredentialBlob or not credential.CredentialBlobSize:
            return ""
        return ctypes.wstring_at(credential.CredentialBlob, credential.CredentialBlobSize // 2).rstrip("\0").strip()
    finally:
        if pointer:
            ctypes.windll.advapi32.CredFree(pointer)


def _document_bridge_token() -> str:
    return os.environ.get("QR_DOCUMENT_BRIDGE_TOKEN", "").strip() or _windows_credential("AIS.DocumentBridgeToken")

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
            "database_path": DATABASE_LABEL
        }
    except Exception as e:
        return {"error": str(e), "database_path": DATABASE_LABEL}

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
        "database_path": DATABASE_LABEL,
        "database_exists": os.path.exists(DB_PATH) if IS_SQLITE else True,
        "env_path": ENV_PATH,
        "env_file_found": env_found,
        "env_loaded": os.getenv("EMAIL_USERNAME") is not None,
        "invoice_path": WATCH_PATH,
        "invoice_source_share_path": SOURCE_SHARE_PATH,
        "local_invoice_inbox_path": LOCAL_INBOX_PATH,
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
        
    data["database_path"] = DATABASE_LABEL
    data["env_file_path"] = ENV_PATH
    data["env_loaded"] = os.getenv("EMAIL_USERNAME") is not None
    
    try:
        data["invoice_share_path"] = SOURCE_SHARE_PATH
        data["local_invoice_inbox_path"] = LOCAL_INBOX_PATH
        exists = os.path.exists(WATCH_PATH)
        data["invoice_watcher_path_reachable"] = exists
        if exists:
            data["pdf_count_in_local_inbox"] = len([f for f in os.listdir(WATCH_PATH) if f.lower().endswith(".pdf")])
        else:
            data["pdf_count_in_local_inbox"] = 0
    except Exception as e:
        data["invoice_watcher_path_reachable"] = False
        data["pdf_count_in_local_inbox"] = f"ERROR: {str(e)}"

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
            
    return {
        "online": online,
        "path": WATCH_PATH,
        "source_share_path": SOURCE_SHARE_PATH,
        "local_inbox_path": LOCAL_INBOX_PATH,
        "label": "Local Invoice Inbox",
        "status_color": "Green" if online else "Red",
        "pdf_count": pdf_count,
        "source_share_available": ingestion_status.get("source_share_available", False),
        "last_sync_error": ingestion_status.get("last_sync_error"),
    }

@app.get("/api/invoices/live-feed")
async def get_live_feed(days: int = 7, per_day: int = 20, db: Session = Depends(get_db)):
    from backend.models import Payment as PaymentModel
    safe_days = max(1, min(days, 31))
    safe_per_day = max(1, min(per_day, 100))
    cutoff = datetime.now() - timedelta(days=safe_days)
    candidate_bills = db.query(Bill).filter(
        Bill.is_test_data == False,
        ~Bill.bill_number.like('TEST-%'),
        ~Bill.bill_number.like('ARCH-%'),
        or_(Bill.invoice_date == None, Bill.invoice_date >= cutoff)
    ).order_by(Bill.invoice_date.desc(), Bill.invoice_generated_at.desc(), Bill.ingested_at.desc()).all()

    bills_by_date = {}
    bills = []
    for bill in candidate_bills:
        effective_date = bill.invoice_date or bill.order_date or bill.invoice_generated_at or bill.created_at
        date_key = effective_date.strftime("%Y-%m-%d") if effective_date else "Unknown Date"
        count = bills_by_date.get(date_key, 0)
        if count >= safe_per_day:
            continue
        bills_by_date[date_key] = count + 1
        bills.append(bill)

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
        
        effective_date = b.invoice_date or b.order_date or b.invoice_generated_at or b.created_at

        results.append({
            "id": b.id,
            "bill_number": b.bill_number,
            "invoice_date": effective_date.strftime("%Y-%m-%d") if effective_date else None,
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

def operational_bills_filter():
    """Filter conditions for production bills (excludes test data and the
    non-production bill-number prefixes used for fixtures/imports/mocks)."""
    return [
        Bill.is_test_data == False,
        ~Bill.bill_number.ilike("TEST-%"),
        ~Bill.bill_number.ilike("ARCH-%"),
        ~Bill.bill_number.ilike("HARDENING-%"),
        ~Bill.bill_number.ilike("MOCK-%"),
    ]

def resolve_operational_date(db: Session) -> str:
    """The business day the dashboard should show.

    Returns today if any production bills are dated today; otherwise the most
    recent business day that actually has invoices. The shop frequently imports
    *prior* days' invoices, so a strict "today" view shows a wall of zeros even
    though there is fresh data — this falls back to the latest real day instead.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_count = db.query(Bill).filter(
        func.date(Bill.invoice_date) == today_str, *operational_bills_filter()
    ).count()
    if today_count > 0:
        return today_str
    latest = db.query(func.max(func.date(Bill.invoice_date))).filter(
        *operational_bills_filter()
    ).scalar()
    return latest or today_str

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

    # Business day shown by the day-scoped cards/sections (falls back to the
    # latest real day when today has no dated bills — see resolve_operational_date).
    operational_date = resolve_operational_date(db)
    is_showing_today = (operational_date == today_str)

    bills_today_query = db.query(Bill).filter(func.date(Bill.invoice_date) == operational_date, *operational_bills_filter())
    total_bills_today = bills_today_query.count()

    unverified_adv_query = db.query(Bill).filter(Bill.is_test_data == False, Bill.advance_amount > 0, Bill.advance_verification_status != "VERIFIED")
    unverified_adv_count = unverified_adv_query.count()
    unverified_adv_amount = float(db.query(func.sum(Bill.advance_amount)).filter(Bill.is_test_data == False, Bill.advance_amount > 0, Bill.advance_verification_status != "VERIFIED").scalar() or 0.0)

    imported_today = db.query(Bill).filter(Bill.created_at >= today_start, Bill.is_test_data == False).count()
    pending_previous = db.query(Bill).filter(func.date(Bill.invoice_date) < operational_date, Bill.is_test_data == False, or_(Bill.status == "Yellow", Bill.status == "Blue", Bill.status == "Purple", Bill.review_required == 1)).count()
    verified_today = bills_today_query.filter(Bill.status == "Green").count()
    review_required_total = db.query(Bill).filter(Bill.review_required == 1, Bill.is_test_data == False).count()
    partial_paid = db.query(Bill).filter(Bill.status == "Blue", Bill.remaining_amount > 0, Bill.is_test_data == False).count()
    total_sale_today = float(db.query(func.sum(Bill.amount)).filter(func.date(Bill.invoice_date) == operational_date, *operational_bills_filter()).scalar() or 0.0)
    cash_in_hand_today = float(db.query(func.sum(Bill.cash_received)).filter(func.date(Bill.invoice_date) == operational_date, *operational_bills_filter()).scalar() or 0.0)
    bank_confirmed_today = float(db.query(
        func.sum(
            func.coalesce(Bill.bank_received, 0)
            + func.coalesce(Bill.card_received, 0)
            + func.coalesce(Bill.sms_confirmed_amount, 0)
            + func.coalesce(Bill.email_confirmed_amount, 0)
        )
    ).filter(func.date(Bill.invoice_date) == operational_date, *operational_bills_filter()).scalar() or 0.0)
    
    # Financial visibility check
    is_owner = user_role in ["OWNER", "ADMIN"]
    
    # Log attempt if non-owner
    if not is_owner:
        from backend.reconciliation.logic import log_audit
        log_audit(db, "System", 0, "FINANCIAL_DATA_ACCESS", user_role, "DENIED", f"User: {actor_id}")
    
    from backend.models import Payment as PaymentModel
    from backend.models import Cheque
    bills_today_ids = [b.id for b in bills_today_query.all()]
    cheques_pending_today = float(db.query(func.sum(Cheque.amount)).filter(
        Cheque.bill_id.in_(bills_today_ids),
        Cheque.status.in_(["Blue", "CHEQUE_DEPOSITED", "CHEQUE_CLEARING", "REALIZING_CHEQUE"])
    ).scalar() or 0.0) if bills_today_ids else 0.0
    latest_invoice_date = db.query(func.max(func.date(Bill.invoice_date))).filter(*operational_bills_filter()).scalar()
    
    # Mandate: Only Owners/Admins see collections
    if is_owner:
        payments_today = db.query(PaymentModel).filter(PaymentModel.bill_id.in_(bills_today_ids)).all()
        verified_adv_today = float(db.query(func.sum(Bill.advance_amount)).filter(Bill.id.in_(bills_today_ids), Bill.advance_verification_status == "VERIFIED").scalar() or 0.0)
        total_collection = float(sum(p.amount for p in payments_today) or 0.0)
        cash_collection = float(sum(p.amount for p in payments_today if p.mode in ["CASH", "OLD_GOLD_EXCHANGE"]) or 0.0)
        cash_collection += verified_adv_today
        bank_collection = float(sum(p.amount for p in payments_today if p.mode in ["BANK_TRANSFER", "CARD", "UPI", "NEFT", "IMPS", "RTGS"]) or 0.0)
        sms_confirmed = float(db.query(func.sum(Bill.sms_confirmed_amount)).filter(func.date(Bill.invoice_date) == operational_date, *operational_bills_filter()).scalar() or 0.0)
        email_confirmed = float(db.query(func.sum(Bill.email_confirmed_amount)).filter(func.date(Bill.invoice_date) == operational_date, *operational_bills_filter()).scalar() or 0.0)
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
        "totalSaleToday": total_sale_today if is_owner else None, "cashInHandToday": cash_in_hand_today if is_owner else None,
        "bankConfirmedToday": bank_confirmed_today if is_owner else None, "chequesPendingToday": cheques_pending_today if is_owner else None,
        "totalReview": review_required_total, "financialDataAvailable": total_bills_today > 0, "latestOperationalDate": latest_invoice_date,
        "operationalDate": operational_date, "isShowingToday": is_showing_today,
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

@app.get("/api/admin/pdf-duplicate-quarantine")
async def get_pdf_duplicate_quarantine(db: Session = Depends(get_db)):
    from backend.invoice_lifecycle import get_duplicate_quarantine_summary
    return get_duplicate_quarantine_summary(db)

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

def _require_lan_bank_activity(request: Request):
    client_host = request.client.host if request.client else ""
    try:
        client_ip = ipaddress.ip_address(client_host)
    except ValueError:
        raise HTTPException(status_code=403, detail="Bank activity is available only on the local network.")
    if not (client_ip.is_loopback or client_ip.is_private):
        raise HTTPException(status_code=403, detail="Bank activity is available only on the local network.")

def _normalise_bank_activity_reference(reference: str) -> str:
    return re.sub(r"\s+", "", (reference or "").strip()).upper()

def _bank_activity_copy_key(reference: str) -> str:
    return f"bank_activity_copy_state:{hashlib.sha256(_normalise_bank_activity_reference(reference).encode('utf-8')).hexdigest()}"

def _bank_activity_copy_states(db: Session) -> Dict[str, int]:
    states: Dict[str, int] = {}
    for setting in db.query(SystemSetting).filter(SystemSetting.key.like("bank_activity_copy_state:%")).all():
        try:
            state = json.loads(setting.value)
            reference = _normalise_bank_activity_reference(str(state.get("reference", "")))
            count = max(0, int(state.get("count", 0)))
            if reference:
                states[reference] = count
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return states

def _bank_activity_copy_colour(count: int) -> str:
    return "red" if count >= 2 else "green" if count == 1 else "blue"

def _bank_activity_row(alert: SMSAlert, direction: str, duplicate: bool = False, correction: Optional[dict] = None, copy_counts: Optional[Dict[str, int]] = None) -> dict:
    """Sanitised live-view record. Deliberately never exposes the raw SMS body."""
    raw_body = alert.raw_body or ""
    parsed = parse_bank_sms(raw_body)
    account = extract_account_display(raw_body) or alert.account_suffix or parsed.account_suffix or "Not recorded"
    counterparty = extract_counterparty(raw_body, direction) or alert.payer_name or parsed.payer_name or "Not recorded"
    timestamp = alert.transaction_timestamp or alert.created_at
    row = {
        "id": alert.id,
        "bank_name": alert.bank_name or parsed.sender_bank or "Not recorded",
        "account": account,
        "counterparty": counterparty,
        "amount": float(alert.amount or 0),
        "date": timestamp.strftime("%d %b %Y") if timestamp else "Not recorded",
        "time": timestamp.strftime("%H:%M:%S") if timestamp else "Not recorded",
        "reference": alert.utr_reference or parsed.utr_reference or "Not recorded",
        "mode": extract_payment_mode(raw_body) or "Not recorded",
        "recorded_at": timestamp.isoformat() if timestamp else None,
        "flags": {
            "duplicate_reference": duplicate,
            "reversal_or_refund": bool(re.search(r"\b(revers(?:ed|al)?|refund|chargeback)\b", raw_body, re.IGNORECASE)),
        },
        "is_corrected": bool(correction),
    }
    for key in ("bank_name", "account", "counterparty", "reference", "mode"):
        value = (correction or {}).get(key)
        if isinstance(value, str) and value.strip():
            row[key] = value.strip()
    copy_count = (copy_counts or {}).get(_normalise_bank_activity_reference(row["reference"]), 0)
    row["copy_count"] = copy_count
    row["copy_state"] = _bank_activity_copy_colour(copy_count)
    return row

def _activity_corrections(db: Session) -> Dict[int, dict]:
    corrections = {}
    for setting in db.query(SystemSetting).filter(SystemSetting.key.like("bank_activity_correction:%")).all():
        try:
            corrections[int(setting.key.rsplit(":", 1)[1])] = json.loads(setting.value)
        except (ValueError, json.JSONDecodeError):
            continue
    return corrections

def _active_bank_activity_test_popups(db: Session) -> List[dict]:
    """Transient, LAN-only test notices. They never become payment records."""
    now = datetime.now()
    active = []
    for setting in db.query(SystemSetting).filter(SystemSetting.key.like("bank_activity_test_popup:%")).all():
        try:
            notice = json.loads(setting.value)
            if datetime.fromisoformat(notice["expires_at"]) > now:
                active.append(notice["alert"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return active


def _notifier_release_directory() -> str:
    return os.path.join(BASE_DIR, "release", "bank-activity-notifier")


@app.get("/api/bank-activity/notifier-release")
async def get_bank_activity_notifier_release(request: Request):
    """LAN-only checksum manifest used by installed native popup clients."""
    _require_lan_bank_activity(request)
    manifest_path = os.path.join(_notifier_release_directory(), "current.json")
    try:
        with open(manifest_path, encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
        filename = os.path.basename(str(manifest["filename"]))
        version = str(manifest["version"])
        digest = str(manifest["sha256"]).lower()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=404, detail="No notifier update is published.")
    if filename != manifest.get("filename") or not re.fullmatch(r"[A-Fa-f0-9]{64}", digest):
        raise HTTPException(status_code=500, detail="Notifier release manifest is invalid.")
    release_path = os.path.join(_notifier_release_directory(), filename)
    if not os.path.isfile(release_path):
        raise HTTPException(status_code=404, detail="Notifier release file is unavailable.")
    root = str(request.base_url).rstrip("/")
    return {
        "version": version,
        "sha256": digest,
        "download_url": f"{root}/api/bank-activity/notifier-release/{filename}",
    }


@app.get("/api/bank-activity/notifier-release/{filename}")
async def download_bank_activity_notifier_release(filename: str, request: Request):
    """Return the exact EXE named by the current LAN release manifest."""
    _require_lan_bank_activity(request)
    safe_filename = os.path.basename(filename)
    if safe_filename != filename:
        raise HTTPException(status_code=404, detail="Release not found.")
    release_path = os.path.join(_notifier_release_directory(), safe_filename)
    if not os.path.isfile(release_path):
        raise HTTPException(status_code=404, detail="Release not found.")
    return FileResponse(release_path, media_type="application/vnd.microsoft.portable-executable", filename=safe_filename)

@app.get("/api/bank-activity")
async def get_bank_activity(request: Request, db: Session = Depends(get_db)):
    """Latest credited/debited bank SMS records for the LAN-only cash-flow view."""
    _require_lan_bank_activity(request)
    history_start = datetime.now() - timedelta(days=30)
    alerts = (
        db.query(SMSAlert)
        .filter(SMSAlert.transaction_timestamp >= history_start)
        .order_by(SMSAlert.transaction_timestamp.desc())
        .limit(500)
        .all()
    )
    reference_counts: Dict[str, int] = {}
    for alert in alerts:
        if alert.utr_reference:
            reference_counts[alert.utr_reference] = reference_counts.get(alert.utr_reference, 0) + 1
    corrections = _activity_corrections(db)
    copy_counts = _bank_activity_copy_states(db)
    credits, debits = [], []
    for alert in alerts:
        # Re-evaluate old records from their source body. Earlier versions saved
        # every relay message as CREDIT, including debit notifications.
        direction = detect_credit_or_debit(alert.raw_body) or (alert.credit_or_debit or "").upper()
        if direction == "CREDIT":
            credits.append(_bank_activity_row(alert, direction, reference_counts.get(alert.utr_reference or "", 0) > 1, corrections.get(alert.id), copy_counts))
        elif direction == "DEBIT":
            debits.append(_bank_activity_row(alert, direction, reference_counts.get(alert.utr_reference or "", 0) > 1, corrections.get(alert.id), copy_counts))
    latest = max((alert.transaction_timestamp for alert in alerts if alert.transaction_timestamp), default=None)
    return {
        "generated_at": datetime.now().isoformat(),
        "history_start": history_start.isoformat(),
        "credits": credits,
        "debits": debits,
        "test_alerts": _active_bank_activity_test_popups(db),
        "health": {
            "last_relay_transaction_at": latest.isoformat() if latest else None,
            "last_email_sync": email_status.get("last_sync"),
            "email_sync_running": bool(email_status.get("is_running")),
            "email_error": email_status.get("last_error"),
        },
    }

@app.post("/api/bank-activity/test-popup")
async def send_bank_activity_test_popup(request: Request, db: Session = Depends(get_db)):
    """Send a harmless test popup to every enabled LAN notifier for one minute."""
    _require_lan_bank_activity(request)
    test_id = f"test-{uuid4().hex}"
    alert = {
        "id": test_id,
        "direction": "CREDIT",
        "bank_name": "ARADHANA TEST",
        "account": "TEST ONLY",
        "counterparty": "Popup verification",
        "amount": 1.00,
        "date": datetime.now().strftime("%d %b %Y"),
        "time": datetime.now().strftime("%H:%M:%S"),
        "reference": "TEST-POPUP-001",
        "mode": "TEST",
        "recorded_at": datetime.now().isoformat(),
        "flags": {"duplicate_reference": False, "reversal_or_refund": False},
        "is_corrected": False,
        "copy_count": 0,
        "copy_state": "blue",
    }
    db.add(SystemSetting(
        key=f"bank_activity_test_popup:{test_id}",
        value=json.dumps({"expires_at": (datetime.now() + timedelta(seconds=60)).isoformat(), "alert": alert}),
    ))
    db.add(AuditLog(entity_type="BankActivity", entity_id=0, action="TEST_POPUP_SENT", actor="LAN_BANK_ACTIVITY", metadata_json=json.dumps({"test_id": test_id})))
    db.commit()
    return {"status": "sent", "test_id": test_id, "expires_in_seconds": 60}

class BankActivityCorrectionInput(BaseModel):
    bank_name: Optional[str] = None
    account: Optional[str] = None
    counterparty: Optional[str] = None
    reference: Optional[str] = None
    mode: Optional[str] = None
    note: Optional[str] = None

class BankActivityReferenceCopiedInput(BaseModel):
    reference: str
    source: str = "dashboard"

@app.post("/api/bank-activity/reference-copied")
async def record_bank_activity_reference_copy(payload: BankActivityReferenceCopiedInput, request: Request, db: Session = Depends(get_db)):
    """Persist reference/UTR copy state centrally for every trusted LAN display."""
    _require_lan_bank_activity(request)
    reference = _normalise_bank_activity_reference(payload.reference)
    if not reference or reference == "NOTRECORDED" or len(reference) > 160:
        raise HTTPException(status_code=400, detail="A valid Ref / UTR is required.")
    source = (payload.source or "dashboard").strip().lower()[:40]
    key = _bank_activity_copy_key(reference)
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    previous_count = 0
    if setting:
        try:
            previous_count = max(0, int(json.loads(setting.value).get("count", 0)))
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            previous_count = 0
    count = previous_count + 1
    state = {"reference": reference, "count": count, "first_copied_at": datetime.now().isoformat() if previous_count == 0 else None, "last_copied_at": datetime.now().isoformat()}
    if setting:
        setting.value = json.dumps(state)
    else:
        db.add(SystemSetting(key=key, value=json.dumps(state)))
    db.add(AuditLog(
        entity_type="BankActivityReference",
        entity_id=0,
        action="REFERENCE_COPIED",
        actor="LAN_BANK_ACTIVITY",
        metadata_json=json.dumps({"reference": reference, "copy_count": count, "source": source, "client_ip": request.client.host if request.client else None}),
    ))
    db.commit()
    return {"reference": reference, "copy_count": count, "copy_state": _bank_activity_copy_colour(count)}

@app.post("/api/bank-activity/{alert_id}/correction")
async def correct_bank_activity(alert_id: int, correction: BankActivityCorrectionInput, request: Request, db: Session = Depends(get_db)):
    """LAN-only display correction. Original SMS and reconciliation evidence stay immutable."""
    _require_lan_bank_activity(request)
    alert = db.query(SMSAlert).filter(SMSAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Bank activity record not found.")
    values = {key: (getattr(correction, key) or "").strip() for key in ("bank_name", "account", "counterparty", "reference", "mode")}
    values = {key: value[:160] for key, value in values.items() if value}
    if not values:
        raise HTTPException(status_code=400, detail="Enter at least one corrected value.")
    values["note"] = (correction.note or "").strip()[:500]
    key = f"bank_activity_correction:{alert_id}"
    previous = get_setting(db, key)
    set_setting(db, key, json.dumps(values))
    db.add(AuditLog(
        entity_type="BankActivity",
        entity_id=alert_id,
        action="LAN_DISPLAY_CORRECTION",
        old_status=previous,
        new_status=json.dumps(values),
        actor="LAN_BANK_ACTIVITY",
        metadata_json=json.dumps({"source": "BankActivityLAN", "note": values["note"], "timestamp": datetime.now().isoformat()}),
    ))
    db.commit()
    return {"status": "saved", "alert_id": alert_id}

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

def iso_or_none(value):
    return value.isoformat() if value else None

def is_operational_reconciliation_bill(bill: Bill) -> bool:
    bill_no = (bill.bill_number or "").upper()
    return (
        not bool(bill.is_test_data)
        and not bill_no.startswith("TEST-")
        and not bill_no.startswith("ARCH-")
        and not bill_no.startswith("HARDENING-")
    )

def requires_accountant_approval(payment_mode: str) -> bool:
    normalized_mode = (payment_mode or "").upper()
    return any(token in normalized_mode for token in (
        "ADVANCE",
        "OLD_GOLD_EXCHANGE",
        "OLD GOLD",
        "CUSTOMER PURCHASE",
        "BUYBACK",
    ))

def reconciliation_confidence(invoice_amount: float, received_amount: float, payment_mode: str = "") -> str:
    if requires_accountant_approval(payment_mode):
        return "Medium"
    if invoice_amount > 0 and received_amount > 0 and abs(invoice_amount - received_amount) < 0.01:
        return "High"
    if 0 < received_amount < invoice_amount:
        return "Medium"
    return "Low"

def reconciliation_display_status(invoice_amount: float, received_amount: float, difference: float, payment_mode: str, stored_status: str) -> str:
    normalized_status = (stored_status or "").upper()
    normalized_mode = (payment_mode or "").upper()
    if requires_accountant_approval(payment_mode):
        return "ACCOUNTANT APPROVAL REQUIRED"
    if difference < -0.01 or normalized_status in {"MISMATCH", "ERROR", "PAYMENT_TOTAL_MISMATCH", "FRAUD_RISK", "RED"}:
        return "Risk / Mismatch"
    if "CHEQUE" in normalized_mode:
        return "Realizing Cheque"
    if invoice_amount > 0 and received_amount > 0 and abs(invoice_amount - received_amount) < 0.01:
        return "Verified"
    if 0 < received_amount < invoice_amount:
        return "Pending"
    return "Pending"

def payment_mode_is_manual(payment_mode: Optional[str]) -> bool:
    normalized_mode = (payment_mode or "").upper()
    return any(token in normalized_mode for token in ("CASH", "MANUAL", "OLD_GOLD_EXCHANGE", "OLD GOLD", "ADVANCE", "CUSTOMER PURCHASE", "BUYBACK"))

def within_evidence_window(candidate_time: Optional[datetime], evidence_time: Optional[datetime], hours: int = 24) -> bool:
    if not candidate_time or not evidence_time:
        return False
    return abs((candidate_time - evidence_time).total_seconds()) <= hours * 3600

def find_payment_evidence(db: Session, payment: Payment, bill: Bill, proofs: List[Union[SMSAlert, BankAlert]]) -> dict:
    proof_details = calculate_payment_proof_status(payment, bill, proofs)

    # Determine proof_url based on proof_status and proof_type
    proof_url = None
    if proof_details["proof_status"] == "verified_proof" and proof_details["proof_id"] is not None:
        if proof_details["proof_type"] == "SMS":
            proof_url = f"/api/reconciliation/proof/sms/{proof_details['proof_id']}"
        elif proof_details["proof_type"] == "Bank":
            proof_url = f"/api/reconciliation/proof/bank/{proof_details['proof_id']}"

    # Determine the reference for display, ensuring non-electronic modes don't show UTR
    display_reference = None
    if payment.mode in ["UPI", "IMPS", "NEFT", "RTGS_OR_CHEQUE", "CARD", "BANK_TRANSFER"]:
        display_reference = payment.utr_reference # Electronic modes show only payment UTR. No fallback to bill.reference_no for display.

    return {
        "source": proof_details["proof_type"] or "Not Recorded",
        "timestamp": None,
        "proof_url": proof_url, # Already correctly determined as None if no verified proof
        "reference": display_reference, # Use the determined display reference
        "proof_label": proof_details["proof_label"], # Always follows helper result
        "confidence_score": proof_details["confidence_score"],
        "confidence_reason": proof_details["confidence_reason"],
        "requires_accountant_review": proof_details["requires_accountant_review"],
    }

def get_file_timestamp(path: Optional[str]) -> Optional[datetime]:
    if not path or not os.path.exists(path):
        return None
    try:
        return datetime.fromtimestamp(os.path.getmtime(path))
    except OSError:
        return None

def best_invoice_timestamp(bill: Bill) -> tuple[Optional[datetime], str, bool]:
    pdf_timestamp = get_file_timestamp(bill.pdf_path)
    candidates = (
        (bill.invoice_generated_at, "invoice_generated_at", True),
        (pdf_timestamp, "pdf_mtime", True),
        (bill.created_at, "created_at", True),
        (bill.invoice_date, "invoice_date", False),
    )
    for value, source, has_time in candidates:
        if value:
            return value, source, has_time
    return None, "not_recorded", False

def require_valid_session(request: Request, db: Session) -> str:
    token = request.headers.get("X-Session-Token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    employee_id = validate_session(db, token)
    if not employee_id:
        raise HTTPException(status_code=401, detail="Session expired")
    return employee_id

@app.get("/api/reconciliation/proof/{proof_type}/{proof_id}")
async def get_reconciliation_proof_preview(proof_type: str, proof_id: int, request: Request, db: Session = Depends(get_db)):
    require_valid_session(request, db)
    normalized_type = proof_type.lower()
    if normalized_type == "sms":
        alert = db.query(SMSAlert).filter(SMSAlert.id == proof_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="SMS proof not found")
        return PlainTextResponse(
            "\n".join([
                "SMS PAYMENT PROOF",
                f"Timestamp: {iso_or_none(alert.transaction_timestamp) or 'Not Recorded'}",
                f"Sender: {alert.sender or 'Not Recorded'}",
                f"Bank: {alert.bank_name or 'Not Recorded'}",
                f"Amount: {float(alert.amount or 0.0)}",
                f"UTR/Reference: {alert.utr_reference or alert.sms_id or 'Not Recorded'}",
                "",
                alert.raw_body or "Payment proof not recorded.",
            ])
        )
    if normalized_type == "bank":
        alert = db.query(BankAlert).filter(BankAlert.id == proof_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="Bank proof not found")
        return PlainTextResponse(
            "\n".join([
                "BANK / EMAIL PAYMENT PROOF",
                f"Timestamp: {iso_or_none(alert.received_at) or 'Not Recorded'}",
                f"Sender: {alert.sender or 'Not Recorded'}",
                f"Bank: {alert.bank_name or 'Not Recorded'}",
                f"Amount: {float(alert.amount or 0.0)}",
                f"UTR/Reference: {alert.utr_reference or 'Not Recorded'}",
                "",
                alert.raw_text or "Payment proof not recorded.",
            ])
        )
    raise HTTPException(status_code=404, detail="Proof type not found")

# Path to the latest Prime manual-report import snapshot produced by the import
# pipeline. Overridable via env; defaults to the standard production location.
PRIME_REPORT_IMPORT_JSON = os.environ.get(
    "PRIME_REPORT_IMPORT_JSON",
    os.path.join(r"C:\Aradhana\PrimeExports", "JSON", "prime_report_import.json"),
)

def _json_safe(obj):
    """Recursively replace NaN/Infinity floats with None so the payload is
    strict-JSON compliant (the Prime export occasionally contains NaN)."""
    import math
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj

@app.get("/api/prime/manual-report-import/latest")
async def get_prime_manual_report_latest(request: Request, db: Session = Depends(get_db)):
    """Return the latest Prime manual-report import snapshot.

    Read-only. Serves the already-validated extraction JSON (shape:
    {timestamp, count, stats, records[]}) consumed by the Prime Extraction
    Review page. Requires a valid session.
    """
    require_valid_session(request, db)
    path = PRIME_REPORT_IMPORT_JSON
    if not os.path.exists(path):
        return JSONResponse(
            status_code=404,
            content={"detail": "No Prime manual report import found yet."},
        )
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # pragma: no cover - defensive file/JSON guard
        logger.error(f"Failed to read Prime manual report import at {path}: {exc}")
        raise HTTPException(
            status_code=500, detail="Could not read Prime manual report import."
        )
    return JSONResponse(content=_json_safe(data))

def _escalation_severity(display_status: str) -> str:
    """Owner-escalation severity derived from the reconciliation display status."""
    if display_status == "Risk / Mismatch":
        return "CRITICAL"
    if display_status == "ACCOUNTANT APPROVAL REQUIRED":
        return "HIGH"
    return "MEDIUM"

@app.get("/api/escalations/open")
async def get_open_escalations_real(request: Request, db: Session = Depends(get_db)):
    """Owner escalations — operational bills the reconciliation engine flags as
    needing owner attention.

    An escalation is a non-test, undelivered bill whose computed reconciliation
    status is a problem state: "Risk / Mismatch" (CRITICAL) or
    "ACCOUNTANT APPROVAL REQUIRED" (HIGH). This reuses the SAME classifiers as
    /api/reconciliation/open so the two views can never drift apart. Ordinary
    pending bills stay in the reconciliation queue and are NOT escalated.
    Requires a valid session.
    """
    require_valid_session(request, db)

    bills = (
        db.query(Bill)
        .filter(
            Bill.is_test_data == False,
            ~Bill.bill_number.ilike("TEST-%"),
            ~Bill.bill_number.ilike("ARCH-%"),
            ~Bill.bill_number.ilike("HARDENING-%"),
            Bill.is_delivered == False,
        )
        .order_by(Bill.invoice_generated_at.desc().nullslast(), Bill.created_at.desc())
        .limit(1000)
        .all()
    )

    ESCALATION_STATUSES = {"Risk / Mismatch", "ACCOUNTANT APPROVAL REQUIRED"}
    escalations = []
    for bill in bills:
        if not is_operational_reconciliation_bill(bill):
            continue

        payments = db.query(Payment).filter(Payment.bill_id == bill.id).all()
        payment_total = sum(float(p.amount or 0.0) for p in payments)
        fallback_total = (
            float(bill.cash_received or 0.0)
            + float(bill.bank_received or 0.0)
            + float(bill.card_received or 0.0)
        )
        received_amount = payment_total if payment_total > 0 else fallback_total
        invoice_amount = float(bill.amount or 0.0)
        difference = round(invoice_amount - received_amount, 2)
        payment_mode = bill.payment_mode or ", ".join(p.mode for p in payments if p.mode) or "UNKNOWN"
        display_status = reconciliation_display_status(
            invoice_amount, received_amount, difference, payment_mode, bill.status
        )
        if display_status not in ESCALATION_STATUSES:
            continue

        invoice_ts, _, _ = best_invoice_timestamp(bill)
        escalations.append({
            "escalation_id": f"BILL-{bill.id}",
            "bill_id": bill.id,
            "bill_no": bill.bill_number,
            "customer_name": bill.customer_name or "Unknown",
            "invoice_amount": invoice_amount,
            "received_amount": received_amount,
            "difference": difference,
            "payment_mode": payment_mode,
            "reason": display_status,
            "severity": _escalation_severity(display_status),
            "status": bill.status,
            "confidence": reconciliation_confidence(invoice_amount, received_amount, payment_mode),
            "invoice_date": iso_or_none(bill.invoice_date),
            "invoice_timestamp": iso_or_none(invoice_ts),
            "pdf_available": bool(bill.pdf_path),
        })

    severity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    escalations.sort(key=lambda e: (severity_rank.get(e["severity"], 9), -e["invoice_amount"]))
    return JSONResponse(content={
        "count": len(escalations),
        "critical_count": sum(1 for e in escalations if e["severity"] == "CRITICAL"),
        "high_count": sum(1 for e in escalations if e["severity"] == "HIGH"),
        "escalations": escalations,
    })

# ── KYC document fields (OCR'd Aadhaar/PAN/bank documents) ──────────────────
# Storage follows the exact SystemSetting + per-item copy-state pattern
# already proven on Bank Activity (see _bank_activity_copy_key /
# _bank_activity_copy_colour above) -- but keyed per FIELD within a document,
# since each field (name, account number, IFSC...) gets its own copy button.
KYC_FIELD_LABELS = {
    "name": "Name",
    "address": "Address",
    "document_number": "Document Number",
    "bank_name": "Bank Name",
    "account_number": "Account Number",
    "branch": "Branch",
    "ifsc_code": "IFSC Code",
}


def store_kyc_extraction(doc_id: str, fields: dict, needs_review: list, db: Session) -> None:
    """Called by the KYC-OCR consumer poller once extraction finishes for one
    document. Not exposed as an HTTP endpoint -- the consumer runs on this
    same machine and calls this directly."""
    record = {
        "doc_id": doc_id,
        "fields": fields,
        "needs_review": needs_review,
        "extracted_at": datetime.now().isoformat(),
    }
    key = f"kyc_document:{doc_id}"
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting:
        setting.value = json.dumps(record)
    else:
        db.add(SystemSetting(key=key, value=json.dumps(record)))
    db.add(AuditLog(
        entity_type="KYCDocument", entity_id=0, action="KYC_EXTRACTED",
        actor="LOCAL_KYC_OCR", metadata_json=json.dumps({"doc_id": doc_id, "needs_review": needs_review}),
    ))
    db.commit()


def _kyc_field_copy_key(doc_id: str, field: str) -> str:
    return f"kyc_field_copy_state:{hashlib.sha256(f'{doc_id}:{field}'.encode('utf-8')).hexdigest()}"


def _qr_document_request(path: str, method: str = "GET", payload: Optional[dict] = None) -> tuple[bytes, str]:
    """Server-side bridge. Dashboard clients never receive the QR secret."""
    token = _document_bridge_token()
    if not token:
        raise HTTPException(status_code=503, detail="Document bridge is not configured on this server.")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"X-Document-Bridge-Token": token}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = UrlRequest(QR_DOCUMENT_SERVER_URL + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            return response.read(), response.headers.get_content_type()
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise HTTPException(status_code=error.code, detail=detail) from error
    except URLError as error:
        raise HTTPException(status_code=502, detail=f"Document server unavailable: {error.reason}") from error


def _valid_document_id(value: str) -> str:
    if not re.fullmatch(r"DOC-[A-Z0-9-]{4,64}", value or ""):
        raise HTTPException(status_code=400, detail="Invalid document bundle id.")
    return value


@app.get("/api/documents")
async def get_document_dashboard(request: Request):
    _require_lan_bank_activity(request)
    raw, _ = _qr_document_request("/api/document-bundles/dashboard")
    return JSONResponse(content=json.loads(raw))


@app.get("/api/documents/{bundle_id}/files/{filename}")
async def download_document_file(bundle_id: str, filename: str, request: Request):
    _require_lan_bank_activity(request)
    _valid_document_id(bundle_id)
    if filename != os.path.basename(filename):
        raise HTTPException(status_code=400, detail="Invalid document filename.")
    raw, content_type = _qr_document_request(f"/document-media/{quote(bundle_id)}/{quote(filename)}")
    return Response(content=raw, media_type=content_type or "application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.post("/api/documents/{bundle_id}/reprint")
async def reprint_document(bundle_id: str, request: Request):
    _require_lan_bank_activity(request)
    _valid_document_id(bundle_id)
    raw, _ = _qr_document_request(f"/api/document-bundles/{quote(bundle_id)}/reprint", "POST", {})
    return JSONResponse(content=json.loads(raw))


@app.post("/api/documents/{bundle_id}/resend-to-biller")
async def resend_document_to_biller(bundle_id: str, request: Request):
    _require_lan_bank_activity(request)
    _valid_document_id(bundle_id)
    raw, _ = _qr_document_request(f"/api/document-bundles/{quote(bundle_id)}/resend-to-biller", "POST", {})
    return JSONResponse(content=json.loads(raw))


@app.get("/api/kyc-documents/open")
async def get_open_kyc_documents(request: Request, db: Session = Depends(get_db)):
    """Recent OCR'd KYC documents, each field individually copy-tracked
    (same blue/green/red pattern as Bank Activity references). Lives on the
    Bank Activity LAN console, so it follows that page's access model
    (LAN-restricted, no login) rather than session auth -- matching, not
    weakening, since the rest of that page already shows equally sensitive
    data the same way."""
    _require_lan_bank_activity(request)
    settings = (
        db.query(SystemSetting)
        .filter(SystemSetting.key.like("kyc_document:%"))
        .order_by(SystemSetting.key.desc())
        .limit(50)
        .all()
    )
    documents = []
    for setting in settings:
        try:
            record = json.loads(setting.value)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        doc_id = record.get("doc_id", "")
        field_rows = []
        for field_key, label in KYC_FIELD_LABELS.items():
            value = (record.get("fields") or {}).get(field_key)
            copy_key = _kyc_field_copy_key(doc_id, field_key)
            copy_setting = db.query(SystemSetting).filter(SystemSetting.key == copy_key).first()
            count = 0
            if copy_setting:
                try:
                    count = max(0, int(json.loads(copy_setting.value).get("count", 0)))
                except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                    count = 0
            field_rows.append({
                "field": field_key,
                "label": label,
                "value": value,
                "needs_review": field_key in (record.get("needs_review") or []),
                "copy_count": count,
                "copy_state": _bank_activity_copy_colour(count),
            })
        documents.append({
            "doc_id": doc_id,
            "extracted_at": record.get("extracted_at"),
            "fields": field_rows,
        })
    return JSONResponse(content={"documents": documents})


class KYCFieldCopiedInput(BaseModel):
    doc_id: str
    field: str
    source: str = "dashboard"


@app.post("/api/kyc-documents/field-copied")
async def record_kyc_field_copy(payload: KYCFieldCopiedInput, request: Request, db: Session = Depends(get_db)):
    _require_lan_bank_activity(request)
    if payload.field not in KYC_FIELD_LABELS:
        raise HTTPException(status_code=400, detail="Unknown field.")
    key = _kyc_field_copy_key(payload.doc_id, payload.field)
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    previous_count = 0
    if setting:
        try:
            previous_count = max(0, int(json.loads(setting.value).get("count", 0)))
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            previous_count = 0
    count = previous_count + 1
    state = {"doc_id": payload.doc_id, "field": payload.field, "count": count, "last_copied_at": datetime.now().isoformat()}
    if setting:
        setting.value = json.dumps(state)
    else:
        db.add(SystemSetting(key=key, value=json.dumps(state)))
    db.add(AuditLog(
        entity_type="KYCField", entity_id=0, action="FIELD_COPIED", actor="LOCAL_KYC_OCR",
        metadata_json=json.dumps({"doc_id": payload.doc_id, "field": payload.field, "copy_count": count, "source": payload.source}),
    ))
    db.commit()
    return {"doc_id": payload.doc_id, "field": payload.field, "copy_count": count, "copy_state": _bank_activity_copy_colour(count)}

@app.get("/api/reconciliation/open")
async def get_open_reconciliation_real(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.headers.get("X-Session-Token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not validate_session(db, token):
        raise HTTPException(status_code=401, detail="Session expired")

    considered_query = db.query(Bill).filter(Bill.is_test_data == False)
    total_considered = considered_query.count()
    excluded_test_prefix = considered_query.filter(Bill.bill_number.ilike("TEST-%")).count()
    excluded_archive_prefix = considered_query.filter(Bill.bill_number.ilike("ARCH-%")).count()
    excluded_hardening_prefix = considered_query.filter(Bill.bill_number.ilike("HARDENING-%")).count()
    excluded_test_data = db.query(Bill).filter(Bill.is_test_data == True).count()

    bills = (
        db.query(Bill)
        .filter(
            Bill.is_test_data == False,
            ~Bill.bill_number.ilike("TEST-%"),
            ~Bill.bill_number.ilike("ARCH-%"),
            ~Bill.bill_number.ilike("HARDENING-%"),
        )
        .order_by(Bill.invoice_generated_at.desc().nullslast(), Bill.created_at.desc())
        .limit(1000)
        .all()
    )

    rows = []
    for bill in bills:
        if not is_operational_reconciliation_bill(bill):
            continue
        
        payments = (
            db.query(Payment)
            .filter(Payment.bill_id == bill.id)
            .order_by(Payment.payment_date.asc().nullslast(), Payment.created_at.asc())
            .all()
        )

        proof_eligible_modes = {"UPI", "BANK_TRANSFER", "CARD", "RTGS_OR_CHEQUE"}
        proof_utr_values = {
            payment.utr_reference
            for payment in payments
            if payment.mode in proof_eligible_modes and payment.utr_reference
        }
        proof_amount_values = {
            payment.amount
            for payment in payments
            if payment.mode in proof_eligible_modes and payment.amount is not None
        }
        bank_proof_filters = []
        sms_proof_filters = []
        if proof_utr_values:
            bank_proof_filters.append(BankAlert.utr_reference.in_(proof_utr_values))
            sms_proof_filters.append(SMSAlert.utr_reference.in_(proof_utr_values))
        if proof_amount_values:
            bank_proof_filters.append(BankAlert.amount.in_(proof_amount_values))
            sms_proof_filters.append(SMSAlert.amount.in_(proof_amount_values))

        all_bank_alerts = db.query(BankAlert).filter(or_(*bank_proof_filters)).all() if bank_proof_filters else []
        all_sms_alerts = db.query(SMSAlert).filter(or_(*sms_proof_filters)).all() if sms_proof_filters else []
        all_proofs = all_bank_alerts + all_sms_alerts
        payment_total = sum(float(payment.amount or 0.0) for payment in payments)
        fallback_total = (
            float(bill.cash_received or 0.0)
            + float(bill.bank_received or 0.0)
            + float(bill.card_received or 0.0)
        )
        received_amount = payment_total if payment_total > 0 else fallback_total
        invoice_amount = float(bill.amount or 0.0)
        difference = round(invoice_amount - received_amount, 2)
        payment_mode = bill.payment_mode or ", ".join(payment.mode for payment in payments if payment.mode) or "UNKNOWN"
        confidence = reconciliation_confidence(invoice_amount, received_amount, payment_mode)
        status = reconciliation_display_status(invoice_amount, received_amount, difference, payment_mode, bill.status)
        invoice_timestamp, invoice_timestamp_source, invoice_time_recorded = best_invoice_timestamp(bill)
        payment_breakdown = []
        for payment in payments:
            evidence = find_payment_evidence(db, payment, bill, all_proofs)
            payment_breakdown.append({
                "amount": float(payment.amount or 0.0),
                "mode": payment.mode or "UNKNOWN",
                "timestamp": iso_or_none(payment.payment_date) or evidence["timestamp"] or iso_or_none(payment.created_at),
                "utr_reference": payment.utr_reference,
                "reference": evidence["reference"] or payment.utr_reference or payment.cheque_number,
                "source": evidence["source"],
                "proof_url": evidence["proof_url"],
                "proof_label": evidence["proof_label"],
            })
        if not payment_breakdown and received_amount > 0:
            for mode, amount in (
                ("CASH", float(bill.cash_received or 0.0)),
                ("BANK", float(bill.bank_received or 0.0)), # Note: 'BANK' here is a placeholder, actual bank payments have Payment objects
                ("CARD", float(bill.card_received or 0.0)), # Note: 'CARD' here is a placeholder, actual card payments have Payment objects
            ):
                if amount > 0:
                    fallback_time = bill.invoice_generated_at or bill.created_at or bill.invoice_date
                    
                    # Manually determine proof details based on mode rules, without Payment object
                    proof_details = {
                        "proof_status": "no_proof",
                        "proof_type": None,
                        "proof_id": None,
                        "proof_label": "No proof found",
                        "confidence_score": 0,
                        "confidence_reason": "No explicit payment record or proof found",
                        "requires_accountant_review": True
                    }

                    current_utr_reference = bill.reference_no if mode == "BANK" else None

                    if mode == "CASH":
                        proof_details.update({
                            "proof_status": "confirmed_received",
                            "proof_type": "Cash",
                            "proof_label": "Cash auto-confirmed",
                            "confidence_score": 100,
                            "confidence_reason": "Auto-confirmed as per policy (CASH payments)",
                            "requires_accountant_review": False
                        })
                    elif mode in ["ADVANCE", "OLD_GOLD_EXCHANGE"]: # Though these shouldn't be here in fallback, good to be explicit
                        proof_details.update({
                            "proof_status": "pending_accountant_review",
                            "proof_type": mode,
                            "proof_label": f"Accountant review required for {mode}",
                            "confidence_score": 0,
                            "confidence_reason": f"Requires manual accountant confirmation for {mode}",
                            "requires_accountant_review": True
                        })
                    elif mode in ["BANK", "CARD"]:
                        # For implicit bank/card payments, we still check against proofs
                        # This mimics the calculate_payment_proof_status logic for these implicit entries
                        found_match = False
                        for proof in all_proofs:
                            proof_utr = None
                            proof_amount = None
                            proof_type_str = None
                            proof_id = None

                            if isinstance(proof, SMSAlert):
                                proof_utr = proof.utr_reference
                                proof_amount = proof.amount
                                proof_type_str = "SMS"
                                proof_id = proof.id
                            elif isinstance(proof, BankAlert):
                                proof_utr = proof.utr_reference
                                proof_amount = proof.amount
                                proof_type_str = "Bank"
                                proof_id = proof.id
                            
                            # Check for exact match: UTR and Amount
                            if (current_utr_reference and proof_utr and current_utr_reference == proof_utr and
                                abs(float(amount) - float(proof_amount)) < 0.01):
                                proof_details.update({
                                    "proof_status": "verified_proof",
                                    "proof_type": proof_type_str,
                                    "proof_id": proof_id,
                                    "proof_label": f"Verified by {proof_type_str} Proof (ID: {proof_id})",
                                    "confidence_score": 100,
                                    "confidence_reason": f"Exact UTR and amount match with {proof_type_str} proof.",
                                    "requires_accountant_review": False
                                })
                                found_match = True
                                break # Found exact match, no need to check other proofs
                            
                            # Check for partial match: Amount only (if UTR is missing or mismatched)
                            if (not found_match and abs(float(amount) - float(proof_amount)) < 0.01 and
                                (not current_utr_reference or not proof_utr or current_utr_reference != proof_utr)):
                                proof_details.update({
                                    "proof_status": "mismatch_proof",
                                    "proof_type": proof_type_str,
                                    "proof_id": proof_id,
                                    "proof_label": f"Partial Proof from {proof_type_str} (ID: {proof_id}): Amount matches, UTR differs/missing",
                                    "confidence_score": 50,
                                    "confidence_reason": f"Amount matches {proof_type_str} proof, but UTR is missing or mismatched.",
                                    "requires_accountant_review": True
                                })
                                # Don't break, keep looking for exact matches
                        
                        if found_match:
                            pass # Already updated in the loop
                        elif proof_details["proof_status"] != "mismatch_proof": # If no exact match and no partial match
                            proof_details.update({
                                "proof_status": "no_proof",
                                "proof_type": None,
                                "proof_id": None,
                                "proof_label": "No proof found for bank/online payment",
                                "confidence_score": 0,
                                "confidence_reason": "No matching SMS or Bank proof found for bank/online payment.",
                                "requires_accountant_review": True
                            })

                    # Determine proof_url based on proof_details
                    proof_url = None
                    if proof_details["proof_status"] == "verified_proof" and proof_details["proof_id"] is not None:
                        if proof_details["proof_type"] == "SMS":
                            proof_url = f"/api/reconciliation/proof/sms/{proof_details['proof_id']}"
                        elif proof_details["proof_type"] == "Bank":
                            proof_url = f"/api/reconciliation/proof/bank/{proof_details['proof_id']}"

                    payment_breakdown.append({
                        "amount": amount,
                        "mode": mode,
                        "timestamp": iso_or_none(fallback_time),
                        "utr_reference": current_utr_reference,
                        "reference": current_utr_reference,
                        "source": proof_details["proof_type"] or "Manual",
                        "proof_url": proof_url,
                        "proof_label": proof_details["proof_label"],
                        "confidence_score": proof_details["confidence_score"],
                        "confidence_reason": proof_details["confidence_reason"],
                        "requires_accountant_review": proof_details["requires_accountant_review"],
                    })
        rows.append({
            "bill_id": bill.id,
            "bill_no": bill.bill_number,
            "customer_name": bill.customer_name or "",
            "invoice_amount": invoice_amount,
            "bank_amount": received_amount,
            "difference": difference,
            "payment_mode": payment_mode,
            "confidence": confidence,
            "status": status,
            "invoice_date": iso_or_none(bill.invoice_date),
            "invoice_generated_at": iso_or_none(bill.invoice_generated_at),
            "invoice_timestamp": iso_or_none(invoice_timestamp),
            "invoice_timestamp_source": invoice_timestamp_source,
            "invoice_time_recorded": invoice_time_recorded,
            "pdf_mtime": iso_or_none(get_file_timestamp(bill.pdf_path)),
            "invoice_pdf_url": f"/api/invoices/pdf/{bill.id}" if bill.pdf_path else None,
            "invoice_pdf_available": bool(bill.pdf_path),
            "bank_time": None,
            "verified_at": None,
            "verified_by": None,
            "utr_reference": bill.reference_no or next((payment.utr_reference for payment in payments if payment.utr_reference), None),
            "review_age": None,
            "source_system": "ARADHANA_BILLS",
            "has_special_payment_flag": requires_accountant_approval(payment_mode),
            "payment_breakdown": payment_breakdown,
        })

    response.headers["X-Reconciliation-Total-Considered"] = str(total_considered)
    response.headers["X-Reconciliation-Rows-Returned"] = str(len(rows))
    response.headers["X-Reconciliation-Excluded-Test-Prefix"] = str(excluded_test_prefix)
    response.headers["X-Reconciliation-Excluded-Archive-Prefix"] = str(excluded_archive_prefix)
    response.headers["X-Reconciliation-Excluded-Hardening-Prefix"] = str(excluded_hardening_prefix)
    response.headers["X-Reconciliation-Excluded-Test-Data"] = str(excluded_test_data)
    return rows

@app.get("/status-colors")
def status_colors():
    return {"Yellow": "#FFFF99", "Orange": "#FFA500", "Red": "#FF0000", "Green": "#008000", "Blue": "#ADD8E6", "Purple": "#800080"}

app.include_router(api_router)

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

PERMISSION_GROUPS = [
    "dashboard_access",
    "reconciliation_access",
    "reports_access",
    "extraction_review_access",
    "audit_logs_access",
    "master_console_access",
    "user_management_access",
    "emergency_controls_access",
    "financial_metrics_access",
]

ROLE_PERMISSION_PRESETS: Dict[str, List[str]] = {
    "OWNER": PERMISSION_GROUPS,
    "ADMIN": [
        "dashboard_access",
        "reconciliation_access",
        "reports_access",
        "extraction_review_access",
        "audit_logs_access",
        "master_console_access",
        "user_management_access",
    ],
    "ACCOUNTANT": [
        "dashboard_access",
        "reconciliation_access",
        "reports_access",
        "extraction_review_access",
        "audit_logs_access",
    ],
    "STAFF": [
        "dashboard_access",
        "extraction_review_access",
    ],
    "DEVELOPER": [
        "dashboard_access",
        "audit_logs_access",
    ],
    "VIEWER": [
        "dashboard_access",
        "reports_access",
        "audit_logs_access",
    ],
}

UNSAFE_PERMISSION_BY_ROLE: Dict[str, List[str]] = {
    "DEVELOPER": ["financial_metrics_access", "emergency_controls_access"],
    "ACCOUNTANT": ["financial_metrics_access", "emergency_controls_access", "user_management_access"],
    "STAFF": ["financial_metrics_access", "emergency_controls_access", "user_management_access", "master_console_access"],
    "VIEWER": ["financial_metrics_access", "emergency_controls_access", "user_management_access", "master_console_access", "reconciliation_access", "extraction_review_access"],
}

def normalize_role(role: str) -> str:
    normalized = (role or "").strip().upper()
    if normalized not in ROLE_PERMISSION_PRESETS:
        raise HTTPException(status_code=400, detail="Unsupported user role")
    return normalized

def normalize_permissions(role: str, permissions: Optional[List[str]]) -> List[str]:
    requested = permissions if permissions is not None else ROLE_PERMISSION_PRESETS[role]
    normalized = []
    invalid = []
    for permission in requested:
        key = str(permission).strip().lower()
        if key not in PERMISSION_GROUPS:
            invalid.append(key)
        elif key not in normalized:
            normalized.append(key)
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported permission groups: {', '.join(invalid)}")
    unsafe = [p for p in normalized if p in UNSAFE_PERMISSION_BY_ROLE.get(role, [])]
    if unsafe:
        raise HTTPException(status_code=400, detail=f"Unsafe permission groups for {role}: {', '.join(unsafe)}")
    return normalized

def setting_key(kind: str, employee_id: str) -> str:
    return f"user_{kind}:{employee_id}"

def get_setting(db: Session, key: str) -> Optional[str]:
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return setting.value if setting else None

def set_setting(db: Session, key: str, value: str):
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting:
        setting.value = value
    else:
        db.add(SystemSetting(key=key, value=value))

def get_user_permissions(db: Session, user: User) -> List[str]:
    stored = get_setting(db, setting_key("permissions", user.employee_id or ""))
    if stored:
        try:
            parsed = json.loads(stored)
            if isinstance(parsed, list):
                return normalize_permissions(normalize_role(user.role), parsed)
        except (json.JSONDecodeError, HTTPException):
            pass
    return ROLE_PERMISSION_PRESETS.get(normalize_role(user.role), [])

def is_user_archived(db: Session, user: User) -> bool:
    return get_setting(db, setting_key("archived", user.employee_id or "")) == "true"

def safe_user_response(db: Session, user: User) -> Dict[str, Any]:
    archived = is_user_archived(db, user)
    employee_id = user.employee_id or ""
    return {
        "id": user.id,
        "employee_id": employee_id,
        "name": user.name,
        "email": user.email,
        "security_email": user.security_email,
        "role": user.role,
        "is_active": user.is_active == 1,
        "password_reset_required": bool(user.password_reset_required),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "is_archived": archived,
        "is_migrated": employee_id.startswith("MIGRATED-"),
        "is_test_user": employee_id.startswith("TEST-"),
        "permissions": get_user_permissions(db, user),
    }

def log_user_audit(db: Session, actor: User, target: User, action: str, changed_fields: Dict[str, Any]):
    audit = AuditLog(
        entity_type="User",
        entity_id=target.id,
        action=action,
        old_status=None,
        new_status=target.role,
        actor=actor.employee_id,
        metadata_json=json.dumps({
            "actor_employee_id": actor.employee_id,
            "target_employee_id": target.employee_id,
            "changed_fields": changed_fields,
            "timestamp": datetime.now().isoformat(),
            "source": "MasterConsoleUserManagement",
        })
    )
    db.add(audit)

# MASTER CONSOLE: User Administration
@app.get("/api/admin/users")
async def list_users(
    include_inactive: bool = False,
    include_archived: bool = False,
    include_test: bool = False,
    role: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    owner: User = Depends(require_owner)
):
    users = db.query(User).all()
    role_filter = role.upper() if role else None
    search_filter = search.lower().strip() if search else None
    visible_users = []
    for user in users:
        employee_id = user.employee_id or ""
        archived = is_user_archived(db, user)
        is_migrated = employee_id.startswith("MIGRATED-")
        is_test_user = employee_id.startswith("TEST-")
        if not include_inactive and user.is_active != 1:
            continue
        if not include_archived and (archived or is_migrated):
            continue
        if not include_test and is_test_user:
            continue
        if role_filter and user.role.upper() != role_filter:
            continue
        if search_filter:
            haystack = " ".join([
                employee_id,
                user.name or "",
                user.email or "",
                user.security_email or "",
            ]).lower()
            if search_filter not in haystack:
                continue
        visible_users.append(safe_user_response(db, user))
    return visible_users

class UserCreate(BaseModel):
    employee_id: str
    name: str
    email: Optional[str] = None
    security_email: Optional[str] = None
    role: str
    password: Optional[str] = None
    permissions: Optional[List[str]] = None
    send_otp_to_security_email: bool = False
    password_reset_required: bool = True
    is_active: bool = True

class UserUpdate(BaseModel):
    employee_id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    security_email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password_reset_required: Optional[bool] = None
    permissions: Optional[List[str]] = None

class PasswordResetRequest(BaseModel):
    temporary_password: Optional[str] = None
    send_reset_otp: bool = False

@app.post("/api/admin/users")
async def create_user(request: UserCreate, db: Session = Depends(get_db), owner: User = Depends(require_owner)):
    employee_id = request.employee_id.strip().upper()
    existing = db.query(User).filter(User.employee_id == employee_id).first()
    if not existing and request.email:
        existing = db.query(User).filter(User.email == request.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    role = normalize_role(request.role)
    permissions = normalize_permissions(role, request.permissions)
    password_hash = hash_password(request.password) if request.password else None
    new_user = User(
        employee_id=employee_id,
        name=request.name,
        email=request.email,
        security_email=request.security_email,
        role=role,
        hashed_password=password_hash,
        password_reset_required=request.password_reset_required,
        is_active=1 if request.is_active else 0
    )
    db.add(new_user)
    db.flush()
    set_setting(db, setting_key("permissions", new_user.employee_id), json.dumps(permissions))
    log_user_audit(db, owner, new_user, "USER_CREATED", {
        "employee_id": new_user.employee_id,
        "name": new_user.name,
        "email": new_user.email,
        "security_email": new_user.security_email,
        "role": new_user.role,
        "is_active": new_user.is_active == 1,
        "password_reset_required": bool(new_user.password_reset_required),
        "permissions": permissions,
        "temporary_password_set": bool(request.password),
        "reset_otp_requested": request.send_otp_to_security_email,
    })
    if request.send_otp_to_security_email:
        create_otp(db, new_user.employee_id, is_resend=False)
    db.commit()
    return {"status": "success", "user": safe_user_response(db, new_user)}

@app.patch("/api/admin/users/{employee_id}")
async def update_user(employee_id: str, request: UserUpdate, db: Session = Depends(get_db), owner: User = Depends(require_owner)):
    user = db.query(User).filter(User.employee_id == employee_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    changed_fields: Dict[str, Any] = {}
    if request.employee_id is not None:
        new_employee_id = request.employee_id.strip().upper()
        if new_employee_id != user.employee_id:
            if user.employee_id == owner.employee_id:
                raise HTTPException(status_code=400, detail="Cannot change your own employee ID")
            if db.query(User).filter(User.employee_id == new_employee_id, User.id != user.id).first():
                raise HTTPException(status_code=400, detail="Employee ID already exists")
            old_employee_id = user.employee_id
            permissions = get_user_permissions(db, user)
            archived = is_user_archived(db, user)
            user.employee_id = new_employee_id
            set_setting(db, setting_key("permissions", new_employee_id), json.dumps(permissions))
            set_setting(db, setting_key("archived", new_employee_id), "true" if archived else "false")
            changed_fields["employee_id"] = {"old": old_employee_id, "new": new_employee_id}

    for field in ["name", "email", "security_email"]:
        value = getattr(request, field)
        if value is not None and getattr(user, field) != value:
            changed_fields[field] = {"old": getattr(user, field), "new": value}
            setattr(user, field, value)

    if request.role is not None:
        role = normalize_role(request.role)
        if user.role != role:
            changed_fields["role"] = {"old": user.role, "new": role}
            user.role = role
            if request.permissions is None:
                preset_permissions = ROLE_PERMISSION_PRESETS[role]
                set_setting(db, setting_key("permissions", user.employee_id), json.dumps(preset_permissions))
                changed_fields["permissions"] = preset_permissions

    if request.is_active is not None:
        active_value = 1 if request.is_active else 0
        if user.is_active != active_value:
            if user.id == owner.id and active_value == 0:
                raise HTTPException(status_code=400, detail="Cannot disable yourself")
            changed_fields["is_active"] = {"old": user.is_active == 1, "new": request.is_active}
            user.is_active = active_value

    if request.password_reset_required is not None and bool(user.password_reset_required) != request.password_reset_required:
        changed_fields["password_reset_required"] = {"old": bool(user.password_reset_required), "new": request.password_reset_required}
        user.password_reset_required = request.password_reset_required

    if request.permissions is not None:
        permissions = normalize_permissions(normalize_role(user.role), request.permissions)
        set_setting(db, setting_key("permissions", user.employee_id), json.dumps(permissions))
        changed_fields["permissions"] = permissions
        log_user_audit(db, owner, user, "PERMISSIONS_UPDATED", {"permissions": permissions})

    if changed_fields:
        log_user_audit(db, owner, user, "USER_UPDATED", changed_fields)
        db.commit()

    return {"status": "success", "user": safe_user_response(db, user)}

@app.post("/api/admin/users/{employee_id}/toggle")
async def toggle_user(employee_id: str, db: Session = Depends(get_db), owner: User = Depends(require_owner)):
    user = db.query(User).filter(User.employee_id == employee_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == owner.id:
        raise HTTPException(status_code=400, detail="Cannot disable yourself")

    old_active = user.is_active == 1
    user.is_active = 0 if user.is_active == 1 else 1
    action = "USER_ENABLED" if user.is_active == 1 else "USER_DISABLED"
    log_user_audit(db, owner, user, action, {"is_active": {"old": old_active, "new": user.is_active == 1}})
    db.commit()
    return {"status": "success", "user": safe_user_response(db, user)}

@app.post("/api/admin/users/{employee_id}/reset-password")
async def reset_user_password(employee_id: str, request: PasswordResetRequest, db: Session = Depends(get_db), owner: User = Depends(require_owner)):
    user = db.query(User).filter(User.employee_id == employee_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    actions_performed = []
    
    # Always require a password reset after this operation
    user.password_reset_required = True
    log_user_audit(db, owner, user, "PASSWORD_RESET_REQUESTED", {"reset_required": True})
    actions_performed.append("PASSWORD_RESET_REQUESTED")

    # 1. Set Temporary Password if provided
    if request.temporary_password:
        if len(request.temporary_password) < 8:
            raise HTTPException(status_code=400, detail="Temporary password must be at least 8 characters long")
        user.hashed_password = hash_password(request.temporary_password)
        log_user_audit(db, owner, user, "TEMP_PASSWORD_ASSIGNED", {"source": "MasterConsole"})
        actions_performed.append("TEMP_PASSWORD_ASSIGNED")

    # 2. Send OTP if requested
    if request.send_reset_otp:
        log_user_audit(db, owner, user, "OTP_GENERATED", {"source": "MasterConsole"})
        actions_performed.append("OTP_GENERATED")
        
        otp_result = create_otp(db, user.employee_id, is_resend=True)
        
        if not otp_result.get("otp_sent"):
            # Log the failure before committing any changes and raising an error
            log_user_audit(db, owner, user, "OTP_EMAIL_FAILED", {"reason": otp_result.get("message")})
            db.commit() # Commit password change even if email fails
            raise HTTPException(status_code=500, detail=f"OTP Email Failed: {otp_result.get('message', 'Could not send email. Check server logs and .env configuration.')}")
        
        log_user_audit(db, owner, user, "OTP_EMAIL_SENT", {"email": otp_result.get("email")})
        actions_performed.append("OTP_EMAIL_SENT")

    db.commit()
    
    return {"status": "success", "detail": "Password reset process initiated successfully.", "actions": sorted(list(set(actions_performed)))}

@app.post("/api/admin/users/{employee_id}/archive")
async def archive_user(employee_id: str, db: Session = Depends(get_db), owner: User = Depends(require_owner)):
    user = db.query(User).filter(User.employee_id == employee_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == owner.id:
        raise HTTPException(status_code=400, detail="Cannot archive yourself")
    set_setting(db, setting_key("archived", user.employee_id), "true")
    user.is_active = 0
    log_user_audit(db, owner, user, "USER_ARCHIVED", {"is_archived": True, "is_active": False})
    db.commit()
    return {"status": "success", "user": safe_user_response(db, user)}

@app.post("/api/admin/users/{employee_id}/restore")
async def restore_user(employee_id: str, db: Session = Depends(get_db), owner: User = Depends(require_owner)):
    user = db.query(User).filter(User.employee_id == employee_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    set_setting(db, setting_key("archived", user.employee_id), "false")
    log_user_audit(db, owner, user, "USER_RESTORED", {"is_archived": False})
    db.commit()
    return {"status": "success", "user": safe_user_response(db, user)}

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
    current_mode = mode.value if mode else "PRODUCTION"
    return {"mode": current_mode, "maintenance": current_mode.upper() == "MAINTENANCE"}

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

# MASTER CONSOLE: Financial Health Dashboard
@app.get("/api/admin/financial/health")
async def get_financial_health(db: Session = Depends(get_db), owner: User = Depends(require_owner)):
    from backend.models import Bill, Cheque

    pending_review = db.query(Bill).filter(Bill.review_required == 1, Bill.is_test_data == False).count()
    cheques_pending = db.query(Cheque).filter(Cheque.status != "Green").count()

    # Read-only aggregate: no records or payment statuses are modified here.
    total_invoiced_bank = float(db.query(func.sum(Bill.amount)).filter(Bill.payment_mode.like("%BANK%"), Bill.is_test_data == False).scalar() or 0.0)
    total_confirmed_bank = float(db.query(func.sum(Bill.bank_received)).filter(Bill.is_test_data == False).scalar() or 0.0)

    return {
        "pending_review_count": pending_review,
        "cheques_pending_count": cheques_pending,
        "bank_variance_amount": total_invoiced_bank - total_confirmed_bank,
        "reconciliation_accuracy": round((total_confirmed_bank / total_invoiced_bank * 100), 2) if total_invoiced_bank > 0 else 100.0
    }

# ... rest ...

# Auth Models
class LoginRequest(BaseModel):
    employee_id: str
    password: str

class VerifyRequest(BaseModel):
    employee_id: str
    otp_code: str

# Existing routes
@app.post("/auth/login")
async def login_alias(request: LoginRequest, db: Session = Depends(get_db)):
    return await login(request, db)

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

@app.post("/auth/verify")
async def verify_alias(request: VerifyRequest, db: Session = Depends(get_db), req: Request = None):
    return await verify(request, db, req)

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

    # Case-insensitive lookup to match the login flow (which normalizes the id).
    # If the account no longer exists (archived/deleted) return a clean 401 rather
    # than dereferencing None and 500-ing, which the SPA reads as an auth failure
    # and bounces to /login on every load (a "login loop").
    user = db.query(User).filter(func.lower(User.employee_id) == employee_id.lower()).first()
    if not user:
        raise HTTPException(status_code=401, detail="User account not found")
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
        "/api/bank-activity",
        "/api/kyc-documents",
        "/api/documents",
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

frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(frontend_dist):
    assets_path = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
    
@app.get("/api/dashboard/today-bills")
async def get_dashboard_today_bills(db: Session = Depends(get_db)):
    from backend.models import Bill
    operational_date = resolve_operational_date(db)

    bills = db.query(Bill).filter(
        *operational_bills_filter(),
        func.date(func.coalesce(Bill.invoice_date, func.datetime(Bill.created_at, 'localtime'))) == operational_date
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
    from backend.models import Bill
    operational_date = resolve_operational_date(db)

    payments = db.query(PaymentModel, Bill).join(Bill, PaymentModel.bill_id == Bill.id).filter(
        *operational_bills_filter(),
        func.date(func.coalesce(PaymentModel.payment_date, func.datetime(PaymentModel.created_at, 'localtime'))) == operational_date
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
    return JSONResponse(content=results)

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("debug/"): return JSONResponse(status_code=404, content={"detail": "Not Found"})
        index_path = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_path): return FileResponse(index_path)
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

def _svc_enabled(name: str, default: str = "1") -> bool:
    """Retired-mode gate. Set the env var to 0 to keep a background service off.

    AUDITOR_ENABLE_INGESTION   - PDF ingestion watcher (moves files into C:\Aradhana\DUPLICATE)
    AUDITOR_ENABLE_LIFECYCLE   - invoice lifecycle scheduler (moves files into DUPLICATE/ARCHIVE)
    AUDITOR_ENABLE_EMAIL_POLL  - bank alert email poller (feeds the bank-activity dashboard)
    AUDITOR_ENABLE_KYC_OCR_WARMUP - local KYC-document OCR model warm-up poller. Defaults
                                     OFF (unlike the others) because nothing downstream
                                     consumes it yet -- the actual OCR extraction step
                                     isn't built. Turn on only once that exists, otherwise
                                     this just wastes GPU cycles warming a model for every
                                     /print page load with no benefit.
    AUDITOR_ENABLE_SMS_POLL    - bank alert SMS poller (feeds the bank-activity dashboard)
    """
    return os.getenv(name, default).strip().lower() not in ("0", "false", "no", "off")


@app.on_event("startup")
async def startup_event():
    integrity, err = check_db_integrity()
    if not integrity: logger.critical(f"SHUTDOWN: Database integrity failure: {err}")
    logger.info("Starting Backend Services...")
    if _svc_enabled("AUDITOR_ENABLE_INGESTION"):
        start_ingestion_thread()
        logger.info(f"Watcher startup status: {ingestion_status}")
    else:
        logger.warning("PDF ingestion watcher DISABLED (AUDITOR_ENABLE_INGESTION=0)")
    if _svc_enabled("AUDITOR_ENABLE_EMAIL_POLL"):
        start_email_poller()
    else:
        logger.warning("Email poller DISABLED (AUDITOR_ENABLE_EMAIL_POLL=0)")
    if _svc_enabled("AUDITOR_ENABLE_SMS_POLL"):
        start_sms_poller()
    else:
        logger.warning("SMS poller DISABLED (AUDITOR_ENABLE_SMS_POLL=0)")
    if _svc_enabled("AUDITOR_ENABLE_KYC_OCR_WARMUP", default="0"):
        start_kyc_ocr_warmup_poller()
    else:
        logger.info("KYC-OCR warm-up poller not started (enable with AUDITOR_ENABLE_KYC_OCR_WARMUP=1)")
    if _svc_enabled("AUDITOR_ENABLE_KYC_OCR_CONSUMER", default="0"):
        start_kyc_ocr_consumer()
    else:
        logger.info("KYC-OCR document consumer not started (enable with AUDITOR_ENABLE_KYC_OCR_CONSUMER=1)")
    if _svc_enabled("AUDITOR_ENABLE_LIFECYCLE"):
        start_lifecycle_automation()
    else:
        logger.warning("Invoice lifecycle automation DISABLED (AUDITOR_ENABLE_LIFECYCLE=0)")

if __name__ == "__main__":
    import uvicorn
    cert_path, key_path = r"C:\Aradhana\SSL\cert.pem", r"C:\Aradhana\SSL\key.pem"
    if os.path.exists(cert_path) and os.path.exists(key_path): uvicorn.run("backend.review_api:app", host="0.0.0.0", port=8000, ssl_keyfile=key_path, ssl_certfile=cert_path)
    else: uvicorn.run("backend.review_api:app", host="0.0.0.0", port=8000)

class AccountantVerificationAction(BaseModel):
    bill_id: int
    note: str

@app.post("/api/accountant-verification/approve")
async def approve_accountant_verification(action: AccountantVerificationAction, request: Request, db: Session = Depends(get_db)):
    require_valid_session(request, db)
    from backend.reconciliation.logic import log_audit
    bill = db.query(Bill).filter(Bill.id == action.bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    log_audit(db, "Bill", action.bill_id, "ACCOUNTANT_APPROVE", bill.status, bill.status, action.note)
    db.commit()
    return {"status": "success"}

@app.post("/api/accountant-verification/reject")
async def reject_accountant_verification(action: AccountantVerificationAction, request: Request, db: Session = Depends(get_db)):
    require_valid_session(request, db)
    if not action.note or not action.note.strip():
        raise HTTPException(status_code=400, detail="Action note is required for rejection")
    from backend.reconciliation.logic import log_audit
    bill = db.query(Bill).filter(Bill.id == action.bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    log_audit(db, "Bill", action.bill_id, "ACCOUNTANT_REJECT", bill.status, bill.status, action.note)
    db.commit()
    return {"status": "success"}

@app.post("/api/accountant-verification/further-review")
async def further_review_accountant_verification(action: AccountantVerificationAction, request: Request, db: Session = Depends(get_db)):
    require_valid_session(request, db)
    if not action.note or not action.note.strip():
        raise HTTPException(status_code=400, detail="Action note is required for further review")
    from backend.reconciliation.logic import log_audit
    bill = db.query(Bill).filter(Bill.id == action.bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    log_audit(db, "Bill", action.bill_id, "ACCOUNTANT_FURTHER_REVIEW", bill.status, bill.status, action.note)
    db.commit()
    return {"status": "success"}


