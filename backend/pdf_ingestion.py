import os
import time
import hashlib
import logging
import pdfplumber
import re
import threading
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from sqlalchemy.orm import Session
from backend.database import get_session_factory
from backend import business_registry
from backend.models import Bill, Payment, AuditLog, Cheque
import json


def _alert_emails_for(slug: str) -> list:
    profile = business_registry.load_profile(slug)
    return (profile or {}).get("alert_emails") or []


def _business_name_for_slug(slug: str) -> str:
    profile = business_registry.load_profile(slug)
    return (profile or {}).get("business_name") or "Payment Auditor"

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PDF_Ingestion")

# PART C — SHARE PATH
# Was hardcoded to \\PC2\AradhanaInvoicePDFs — one specific business's own
# network share. Falls back to a local, business-neutral folder now; a real
# deployment sets INVOICE_SHARE_PATH (or, once the pollers are converted to
# loop over every tenant — see database.py's _default_slug docstring — each
# business's own invoice_share_path from its profile).
DEFAULT_SHARE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "invoice_inbox")
os.makedirs(DEFAULT_SHARE, exist_ok=True)
WATCH_PATH = os.getenv("INVOICE_SHARE_PATH", DEFAULT_SHARE)

from backend.invoice_lifecycle import handle_duplicate

# OCR Settings
OCR_ACCELERATION = os.getenv("OCR_ACCELERATION", "auto")
CUDA_AVAILABLE = False
try:
    import torch
    CUDA_AVAILABLE = torch.cuda.is_available()
except ImportError:
    pass

logger.info(f"CUDA Available: {CUDA_AVAILABLE}")
logger.info(f"OCR Acceleration Setting: {OCR_ACCELERATION}")

# Per-tenant status trackers. Used to be one shared global dict — under
# multiple tenants' ingestion running concurrently, every business's
# scan/file/error counts would have stomped on every other business's in
# the same dict, and /api/admin/ingestion-status would show whichever
# tenant's poller last wrote to it rather than the requesting tenant's own.
_ingestion_status: dict[str, dict] = {}
status_lock = threading.Lock()


def _status_for(slug: str, watch_path: str = None) -> dict:
    with status_lock:
        if slug not in _ingestion_status:
            _ingestion_status[slug] = {
                "watcher_running": False,
                "watch_path": watch_path or WATCH_PATH,
                "path_exists": False,
                "pdf_files_found": 0,
                "files_processed": 0,
                "invoices_inserted": 0,
                "skipped_duplicates": 0,
                "failed_files": 0,
                "last_file_seen": None,
                "last_processed_time": None,
                "last_error": None,
                "cuda_active": CUDA_AVAILABLE,
            }
        return _ingestion_status[slug]


def update_status(slug: str, **kwargs):
    st = _status_for(slug)
    with status_lock:
        for key, value in kwargs.items():
            if key in st:
                st[key] = value


def increment_status(slug: str, key, amount=1):
    st = _status_for(slug)
    with status_lock:
        if key in st:
            st[key] += amount

def get_file_hash(file_path):
    sha256_hash = hashlib.sha256()
    try:
        # Wait for file to be accessible/unlocked
        attempts = 0
        while attempts < 5:
            try:
                with open(file_path, "rb") as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
                return sha256_hash.hexdigest()
            except IOError:
                time.sleep(1)
                attempts += 1
        return None
    except Exception as e:
        logger.error(f"Error hashing file {file_path}: {e}")
        return None

def check_share_health(slug: str, watch_path: str):
    exists = os.path.exists(watch_path)
    update_status(slug, path_exists=exists)
    if not exists:
        logger.error(f"[{slug}] Invoice Share Offline: {watch_path} is unavailable.")
        return False
    return True

def parse_pdf(file_path, slug: str = None):
    try:
        text = ""
        metadata = {}
        with pdfplumber.open(file_path) as pdf:
            metadata = pdf.metadata
            for page in pdf.pages:
                text += page.extract_text() + "\n"
        
        # Extract precise generation time
        invoice_gen_at = None
        creation_date = metadata.get("CreationDate")
        if creation_date:
            # Format: D:20260601152211+05'30'
            try:
                clean_date = creation_date.replace("D:", "").split("+")[0].split("-")[0]
                invoice_gen_at = datetime.strptime(clean_date[:14], "%Y%m%d%H%M%S")
            except: pass
            
        if not invoice_gen_at:
            # Fallback to file mtime
            mtime = os.path.getmtime(file_path)
            invoice_gen_at = datetime.fromtimestamp(mtime)

        if not text.strip() and (OCR_ACCELERATION != "cpu"):
            logger.info(f"No text extracted from {file_path}, attempting OCR fallback...")
            pass

        data = {
            "raw_text": text,
            "invoice_generated_at": invoice_gen_at,
            "bill_series": None,
            "bill_number": None,
            "invoice_date": None,
            "customer_name": None,
            "customer_mobile": None,
            "customer_address": None,
            "taxable_value": 0.0,
            "cgst": 0.0,
            "sgst": 0.0,
            "round_off": 0.0,
            "total_amount": 0.0,
            "amount_in_words": None,
            "payments": [],
            "parsed_items_json": "[]",
            "bank_name": None,
            "reference_no": None,
            "payment_mode": "UNKNOWN"
        }

        # 1. Invoice No
        inv_match = re.search(r"Invoice No\.?\s*:\s*([A-Z0-9/-]+)", text)
        if inv_match:
            data["bill_number"] = inv_match.group(1)
            if "-" in data["bill_number"]:
                data["bill_series"] = data["bill_number"].split("-")[0]

        # 2. Date Parsing (Strict)
        # PART A: Invoice Date (Strictly from "Date: DD/MM/YYYY")
        # We look for a line that starts with "Date:" or has "Date:" after "Invoice No"
        invoice_date_match = re.search(r"\bDate\s*[:\s]*(\d{2}[-/]\d{2}[-/]\d{4})", text)
        if invoice_date_match:
            try:
                data["invoice_date"] = datetime.strptime(invoice_date_match.group(1).replace("/", "-"), "%d-%m-%Y")
            except: pass

        # PART B: Order Date (Auxiliary dates in brackets or labeled RO/P2/CO)
        order_date_matches = re.findall(r"(?:C\.O\.No\.|RO-|P2-).*?(\d{2}[-/]\d{2}[-/]\d{4})", text)
        if not order_date_matches:
             order_date_matches = re.findall(r"\((\d{2}[-/]\d{2}[-/]\d{4})\)", text)
             
        if order_date_matches:
            try:
                for d_str in order_date_matches:
                    d_val = datetime.strptime(d_str.replace("/", "-"), "%d-%m-%Y")
                    # If it's different from invoice date, it's likely the order date
                    if d_val != data["invoice_date"]:
                        data["order_date"] = d_val
                        break
                if not data.get("order_date") and order_date_matches:
                     data["order_date"] = datetime.strptime(order_date_matches[0].replace("/", "-"), "%d-%m-%Y")
            except: pass

        # 3. Customer Name
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if "Details of Receiver" in line or "Date:" in line:
                if i + 1 < len(lines):
                    data["customer_name"] = lines[i+1].strip()
                break

        # 4. Mobile No
        mobile_match = re.search(r"Mob No\.?\s*[:\s]*(\d{10})", text)
        if mobile_match:
            data["customer_mobile"] = mobile_match.group(1)

        # 5. Total (Final Billed Amount)
        totals = re.findall(r"\bTotal\s+([\d,]+\.\d{2})", text, re.IGNORECASE)
        if totals:
            data["total_amount"] = float(totals[-1].replace(",", ""))

        # 6. Amount in words & Narration/Payments
        in_narration = False
        words_found = False
        payments = []
        cust_purc_total = 0.0
        advance_total = 0.0
        
        for i, line in enumerate(lines):
            line_upper = line.upper()
            if re.search(r"Total\s+[\d,]+\.\d{2}", line, re.IGNORECASE):
                in_narration = True
                continue
            if "ACK NO" in line_upper:
                in_narration = False
                break
                
            if in_narration:
                if not words_found and "ONLY" in line_upper:
                    data["amount_in_words"] = line.strip()
                    words_found = True
                    continue
                
                # Check for payment rows
                amt_match = re.search(r"([\d,]+\.\d{2})", line)
                if amt_match:
                    amt = float(amt_match.group(1).replace(",", ""))
                    mode = "UNKNOWN"
                    pay_date = None
                    
                    # Try to extract date from line (e.g. UPI 01/06/2026)
                    date_match = re.search(r"(\d{2}[-/]\d{2}[-/]\d{4})", line)
                    if date_match:
                        try:
                            pay_date = datetime.strptime(date_match.group(1).replace("/", "-"), "%d-%m-%Y")
                        except: pass

                    if "CASH" in line_upper: mode = "CASH"
                    elif "UPI" in line_upper: mode = "UPI"
                    elif "IMPS" in line_upper: mode = "IMPS"
                    elif "NEFT" in line_upper: mode = "NEFT"
                    elif any(x in line_upper for x in ["RTGS", "CHEQUE", "CHQ"]): mode = "RTGS_OR_CHEQUE"
                    elif "ADVANCE" in line_upper: 
                        mode = "ADVANCE"
                        advance_total += amt
                    elif "CARD" in line_upper: mode = "CARD"
                    elif "BALANCE" in line_upper: mode = "BALANCE"
                    elif any(x in line_upper for x in ["OLD GOLD", "CUST PURC", "PURCHASE"]): 
                        mode = "OLD_GOLD_EXCHANGE"
                        cust_purc_total += amt

                    
                    if mode != "UNKNOWN":
                        payments.append({
                            "mode": mode, 
                            "amount": amt, 
                            "date": pay_date,
                            "raw": line.strip()
                        })
        
        data["payments"] = payments
        data["customer_purchase_amount"] = cust_purc_total
        data["advance_amount"] = advance_total
        if not payments:
            data["payments"] = [{"mode": "CASH", "amount": data["total_amount"], "raw": "Fallback default"}] # fallback

        # 7. Deep Item Parsing
        items = []
        in_table = False
        for line in lines:
            if "[1 gms]" in line or "Rate" in line:
                in_table = True
                continue
            if in_table:
                if "SUB TOTAL" in line.upper() or "DISCOUNT" in line.upper() or "CGST" in line.upper():
                    break
                if line.strip():
                    items.append({"raw_line": line.strip()})
        data["parsed_items_json"] = json.dumps(items)

        return data
    except Exception as e:
        logger.error(f"Error parsing PDF {file_path}: {e}")
        if slug:
            update_status(slug, last_error=f"Parse Error ({os.path.basename(file_path)}): {str(e)}")
        return None

def process_invoice(file_path, slug: str):
    if not file_path.lower().endswith(".pdf"):
        return

    update_status(slug, last_file_seen=os.path.basename(file_path))

    file_hash = get_file_hash(file_path)
    if not file_hash:
        increment_status(slug, "failed_files")
        return

    db = get_session_factory(slug)()
    try:
        # 1. SHA256 Hash check
        existing_hash = db.query(Bill).filter(Bill.pdf_hash == file_hash).first()
        if existing_hash:
            logger.info(f"Duplicate hash detected for {os.path.basename(file_path)}")
            increment_status(slug, "skipped_duplicates")
            handle_duplicate(file_path, db, reason="Duplicate PDF SHA256 hash")
            return

        invoice_data = parse_pdf(file_path, slug)
        if not invoice_data or not invoice_data["bill_number"]:
            logger.warning(f"Parse Failed: {os.path.basename(file_path)} (No bill number)")
            increment_status(slug, "failed_files")
            from backend.email_notifier import send_red_alert_email
            send_red_alert_email(
                subject=f"RED ALERT: Parse Failure - {os.path.basename(file_path)}",
                body=f"System failed to parse invoice details from file: {file_path}",
                alert_emails=_alert_emails_for(slug), business_name=_business_name_for_slug(slug),
            )
            return

        # 2. 5-point identity check
        # - invoice number
        # - invoice date
        # - customer name
        # - grand total
        # - PDF SHA256 hash (already checked above)
        
        duplicate_bill = db.query(Bill).filter(
            Bill.bill_number == invoice_data["bill_number"],
            Bill.invoice_date == invoice_data["invoice_date"],
            Bill.customer_name == invoice_data["customer_name"],
            Bill.amount == invoice_data["total_amount"]
        ).first()

        if duplicate_bill:
            logger.info(f"Duplicate 5-point match for {invoice_data['bill_number']}")
            increment_status(slug, "skipped_duplicates")
            handle_duplicate(file_path, db, reason="5-point identity match (Number, Date, Customer, Total)")
            return

        # Check for just number match (could be a mistake or update)
        duplicate_num = db.query(Bill).filter(Bill.bill_number == invoice_data["bill_number"]).first()
        if duplicate_num:
            logger.warning(f"Duplicate Number Skip: {invoice_data['bill_number']} (Partial identity match)")
            increment_status(slug, "skipped_duplicates")
            handle_duplicate(file_path, db, reason="Duplicate Invoice Number match")
            return

        modes = [p["mode"] for p in invoice_data["payments"]]
        
        status = "Yellow"
        status_text = "Pending"
        review_required = 1
        
        if all(m in ["CASH", "ADVANCE", "OLD_GOLD_EXCHANGE"] for m in modes):
            status = "Green"
            status_text = "Cleared"
            review_required = 0
        elif "CHEQUE" in modes:
            status = "Blue"
            status_text = "Cheque Pending Review"
        elif "BANK_TRANSFER" in modes or "CARD" in modes:
            status = "Yellow"
            status_text = "Pending Bank Confirmation"

        new_bill = Bill(
            bill_series=invoice_data["bill_series"],
            bill_number=invoice_data["bill_number"],
            invoice_date=invoice_data["invoice_date"],
            invoice_generated_at=invoice_data.get("invoice_generated_at"),
            ingested_at=datetime.now(),
            order_date=invoice_data.get("order_date"),
            customer_name=invoice_data.get("customer_name") or "Unknown",
            customer_mobile=invoice_data.get("customer_mobile"),
            customer_address=invoice_data.get("customer_address"),
            taxable_value=invoice_data["taxable_value"],
            cgst=invoice_data["cgst"],
            sgst=invoice_data["sgst"],
            round_off=invoice_data["round_off"],
            total_amount=invoice_data["total_amount"],
            customer_purchase_amount=invoice_data.get("customer_purchase_amount", 0.0),
            advance_amount=invoice_data.get("advance_amount", 0.0),
            payment_mode=",".join(modes),
            bank_name=invoice_data["bank_name"],
            reference_no=invoice_data["reference_no"],
            status=status,
            status_text=status_text,
            review_required=review_required,
            pdf_path=file_path,
            pdf_hash=file_hash,
            raw_extracted_text=invoice_data["raw_text"],
            parsed_items_json=invoice_data["parsed_items_json"],
            amount_in_words=invoice_data["amount_in_words"],
            cash_received=sum(p["amount"] for p in invoice_data["payments"] if p["mode"] in ["CASH"]),
            bank_received=0.0,
            card_received=0.0,
            remaining_amount=invoice_data["total_amount"] - sum(p["amount"] for p in invoice_data["payments"] if p["mode"] in ["CASH", "ADVANCE", "OLD_GOLD_EXCHANGE"]),
            sms_confirmed_amount=0.0,
            email_confirmed_amount=0.0
        )

        db.add(new_bill)
        db.flush()

        for p in invoice_data["payments"]:
            payment = Payment(
                bill_id=new_bill.id,
                amount=p["amount"],
                mode=p["mode"],
                payment_date=p.get("date"),
                bank_name=new_bill.bank_name,
                utr_reference=new_bill.reference_no if p["mode"] == "BANK_TRANSFER" else None,
                cheque_number=new_bill.reference_no if p["mode"] == "CHEQUE" else None,
                status=status
            )
            db.add(payment)

            if p["mode"] == "CHEQUE":
                cheque = Cheque(
                    bill_id=new_bill.id,
                    cheque_number=new_bill.reference_no or "UNKNOWN",
                    bank_name=new_bill.bank_name,
                    amount=p["amount"],
                    customer_name=new_bill.customer_name,
                    status="Blue"
                )
                db.add(cheque)

        # Re-check total amounts match multi-source sum
        total_payments = sum([p["amount"] for p in invoice_data["payments"]])
        if abs(total_payments - new_bill.total_amount) > 1.0:
            new_bill.status = "Red"
            new_bill.status_text = "Error: PAYMENT_TOTAL_MISMATCH"
            new_bill.review_required = 1
            from backend.email_notifier import send_red_alert_email
            send_red_alert_email(
                subject=f"RED ALERT: Payment Total Mismatch - {new_bill.bill_number}",
                body=f"Invoice {new_bill.bill_number} for {new_bill.customer_name} has a mismatch.\nBilled Total: {new_bill.total_amount}\nSum of Payments: {total_payments}",
                alert_emails=_alert_emails_for(slug), business_name=_business_name_for_slug(slug),
            )

        db.commit()
        logger.info(f"Invoice Inserted: {new_bill.bill_number} from {os.path.basename(file_path)}")

        # TRIGGER RECONCILIATION RETRY for this new bill
        from backend.reconciliation.logic import reconcile_unreconciled_alerts
        reconcile_unreconciled_alerts(db)

        increment_status(slug, "invoices_inserted")
        update_status(slug, last_processed_time=datetime.now().isoformat())

    except Exception as e:
        db.rollback()
        logger.error(f"Database Error processing {file_path}: {e}")
        update_status(slug, last_error=f"DB Error: {str(e)}")
        increment_status(slug, "failed_files")
    finally:
        increment_status(slug, "files_processed")
        db.close()

def perform_scan(slug: str, watch_path: str):
    if not check_share_health(slug, watch_path):
        return

    logger.info(f"[{slug}] Folder scan started: {watch_path!r}")

    try:
        all_files = os.listdir(watch_path)
        pdf_files = [f for f in all_files if f.lower().endswith(".pdf")]
        logger.info(f"[{slug}] PDF files count: {len(pdf_files)}")

        update_status(slug, pdf_files_found=len(pdf_files), path_exists=True)

        for file in pdf_files:
            process_invoice(os.path.join(watch_path, file), slug)

        logger.info(f"[{slug}] Folder scan complete. Total files in folder: {len(all_files)}.")
    except Exception as e:
        logger.error(f"[{slug}] Error scanning folder {watch_path}: {e}")
        update_status(slug, last_error=f"Scan Error: {str(e)}")
        # Keep watcher_running True if path exists as per instructions
        update_status(slug, path_exists=os.path.exists(watch_path))


class InvoiceHandler(FileSystemEventHandler):
    def __init__(self, slug: str):
        self.slug = slug

    def on_created(self, event):
        if not event.is_directory:
            process_invoice(event.src_path, self.slug)

    def on_modified(self, event):
        if not event.is_directory:
            process_invoice(event.src_path, self.slug)


def start_watcher(slug: str, watch_path: str):
    if not check_share_health(slug, watch_path):
        update_status(slug, watcher_running=False)
        # Let it continue to poll health rather than returning

    event_handler = InvoiceHandler(slug)
    observer = Observer()
    observer.schedule(event_handler, watch_path, recursive=False)
    observer.start()
    update_status(slug, watcher_running=True)
    logger.info(f"[{slug}] Realtime watcher/poller active on {watch_path}")

    try:
        while True:
            time.sleep(60)  # Re-verify entire list of pdfs in the folder every minute
            if not os.path.exists(watch_path):
                update_status(slug, path_exists=False, watcher_running=False)
            else:
                if not _status_for(slug)["path_exists"]:
                    logger.info(f"[{slug}] Invoice share re-connected.")
                update_status(slug, path_exists=True, watcher_running=True)
                # Periodic scan to ensure nothing was missed by watcher
                perform_scan(slug, watch_path)
    except Exception as e:
        logger.error(f"[{slug}] Watcher thread crashed: {e}")
        update_status(slug, watcher_running=False, last_error=f"Watcher Crash: {str(e)}")


def _tenant_watch_path(slug: str) -> str:
    """Each business's own invoice_share_path from its profile, falling
    back to the module-level default (env-configurable, business-neutral
    local folder) if that tenant hasn't set one — same convenience fallback
    used throughout this conversion for tenants that haven't configured
    per-tenant ingestion yet."""
    profile = business_registry.load_profile(slug)
    return (profile or {}).get("invoice_share_path") or WATCH_PATH


def start_ingestion_thread():
    """Spawns one scan+watcher thread pair PER registered business, each
    watching that business's own configured invoice share. Used to spawn
    exactly one pair for one hardcoded WATCH_PATH — under multiple
    tenants that would have meant every business's invoices got scanned
    from (and inserted against, via the single shared default-tenant
    SessionLocal) whichever one hardcoded share happened to be configured.

    New businesses onboarded after this function runs need a process
    restart to pick up ingestion — not a live-reload loop yet (tracked
    with the onboarding flow this depends on)."""
    for slug in business_registry.list_businesses():
        watch_path = _tenant_watch_path(slug)
        threading.Thread(target=perform_scan, args=(slug, watch_path), daemon=True).start()
        threading.Thread(target=start_watcher, args=(slug, watch_path), daemon=True).start()

if __name__ == "__main__":
    # Direct-invocation debug path only — start_watcher() blocks forever in
    # its own while-loop, so this only ever actually watches the first
    # registered business when run standalone like this. The real
    # multi-tenant path is start_ingestion_thread() above, used by
    # review_api.py's startup event, which spawns one non-blocking daemon
    # thread pair per business instead of looping synchronously.
    for _slug in business_registry.list_businesses():
        _watch_path = _tenant_watch_path(_slug)
        perform_scan(_slug, _watch_path)
        start_watcher(_slug, _watch_path)
