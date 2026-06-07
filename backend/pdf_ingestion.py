import os
import time
import hashlib
import logging
import shutil
import pdfplumber
import re
import threading
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from sqlalchemy.orm import Session
from backend.database import SessionLocal, engine
from backend.models import Bill, Payment, AuditLog, Cheque
import json

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PDF_Ingestion")

# PART C - INVOICE SOURCE AND LOCAL WATCH PATHS
# The backend watcher only observes the local inbox. A separate sync loop copies
# PDFs from the PC2 share into this folder without deleting or modifying source files.
DEFAULT_SOURCE_SHARE = r"\\PC2\AradhanaInvoicePDFs"
DEFAULT_LOCAL_INBOX = r"C:\AradhanaAuditor\invoice_inbox"
DEFAULT_LOCAL_ARCHIVE = r"C:\AradhanaAuditor\invoice_archive"
DEFAULT_LOCAL_FAILED = r"C:\AradhanaAuditor\invoice_failed"

SOURCE_SHARE_PATH = os.getenv(
    "INVOICE_SHARE_PATH_PRIMARY",
    os.getenv("INVOICE_SOURCE_SHARE_PATH", os.getenv("INVOICE_SHARE_PATH", DEFAULT_SOURCE_SHARE)),
)
LOCAL_INBOX_PATH = os.getenv("LOCAL_INVOICE_INBOX_PATH", DEFAULT_LOCAL_INBOX)
LOCAL_ARCHIVE_PATH = os.getenv("LOCAL_INVOICE_ARCHIVE_PATH", DEFAULT_LOCAL_ARCHIVE)
LOCAL_FAILED_PATH = os.getenv("LOCAL_INVOICE_FAILED_PATH", DEFAULT_LOCAL_FAILED)
WATCH_PATH = os.getenv("INVOICE_WATCH_PATH", LOCAL_INBOX_PATH)

if WATCH_PATH != LOCAL_INBOX_PATH:
    logger.warning(f"WATCH_PATH override is active ({WATCH_PATH}). Local inbox is {LOCAL_INBOX_PATH}.")

from backend.invoice_lifecycle import DUPLICATE_PERMISSION_MESSAGE, handle_duplicate

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

# Global status tracker
ingestion_status = {
    "watcher_running": False,
    "watch_path": WATCH_PATH,
    "active_watch_path": WATCH_PATH,
    "watcher_path": WATCH_PATH,
    "source_share_path": SOURCE_SHARE_PATH,
    "local_inbox_path": LOCAL_INBOX_PATH,
    "local_archive_path": LOCAL_ARCHIVE_PATH,
    "local_failed_path": LOCAL_FAILED_PATH,
    "sync_running": False,
    "source_share_available": False,
    "last_sync_at": None,
    "last_sync_error": None,
    "copied_count": 0,
    "skipped_count": 0,
    "local_pdf_count": 0,
    "path_exists": False,
    "observer_started": False,
    "watcher_mode": "offline",
    "observer_error": None,
    "pdf_files_found": 0,
    "files_processed": 0,
    "invoices_inserted": 0,
    "skipped_duplicates": 0,
    "duplicate_move_failed_permission": 0,
    "duplicate_ignored_until_permission_fixed": 0,
    "failed_files": 0,
    "last_file_seen": None,
    "last_processed_time": None,
    "last_error": None,
    "cuda_active": CUDA_AVAILABLE
}

status_lock = threading.Lock()
thread_state_lock = threading.Lock()
sync_thread_started = False
watcher_thread_started = False
SYNC_INTERVAL_SECONDS = 10

def update_status(**kwargs):
    with status_lock:
        for key, value in kwargs.items():
            if key in ingestion_status:
                ingestion_status[key] = value

def increment_status(key, amount=1):
    with status_lock:
        if key in ingestion_status:
            ingestion_status[key] += amount

def count_local_pdfs():
    try:
        files = os.listdir(WATCH_PATH)
        return len([f for f in files if f.lower().endswith(".pdf")])
    except Exception:
        return 0

def refresh_local_pdf_count():
    pdf_count = count_local_pdfs()
    update_status(local_pdf_count=pdf_count, pdf_files_found=pdf_count)
    return pdf_count

def ensure_local_invoice_dirs():
    for path in (LOCAL_INBOX_PATH, LOCAL_ARCHIVE_PATH, LOCAL_FAILED_PATH, WATCH_PATH):
        os.makedirs(path, exist_ok=True)

def record_duplicate_result(result):
    if not result:
        return
    if result.get("status") == "permission_failed":
        increment_status("duplicate_move_failed_permission")
        update_status(last_error=DUPLICATE_PERMISSION_MESSAGE)
    elif result.get("status") == "ignored_permission":
        increment_status("duplicate_ignored_until_permission_fixed")
        update_status(last_error=DUPLICATE_PERMISSION_MESSAGE)

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

def check_share_health():
    try:
        ensure_local_invoice_dirs()
        files = os.listdir(WATCH_PATH)
        pdf_count = len([f for f in files if f.lower().endswith(".pdf")])
        update_status(
            active_watch_path=WATCH_PATH,
            watcher_path=WATCH_PATH,
            path_exists=True,
            pdf_files_found=pdf_count,
            local_pdf_count=pdf_count,
        )
        return True
    except Exception as e:
        reason = f"{type(e).__name__}: {str(e)}"
        update_status(
            active_watch_path=WATCH_PATH,
            watcher_path=WATCH_PATH,
            path_exists=False,
            last_error=f"Local Watch Path Error: {reason}",
        )
        logger.error(f"Invoice local inbox unavailable: {WATCH_PATH} is unavailable. {reason}")
        return False

def same_file_already_copied(src_path, dest_path):
    try:
        if not os.path.exists(dest_path):
            return False
        if os.path.getsize(src_path) != os.path.getsize(dest_path):
            return False
        src_hash = get_file_hash(src_path)
        dest_hash = get_file_hash(dest_path)
        if src_hash and dest_hash:
            return src_hash == dest_hash
        return True
    except Exception as e:
        logger.warning(f"Unable to compare source and local PDF {src_path} -> {dest_path}: {e}")
        return False

def copy_pdf_to_local_inbox(src_path, dest_path):
    tmp_path = f"{dest_path}.tmp"
    if os.path.exists(dest_path):
        return "exists"
    if os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except Exception as e:
            logger.warning(f"Unable to remove stale temp PDF {tmp_path}: {e}")
            return "temp_blocked"

    shutil.copy2(src_path, tmp_path)
    copied_size = os.path.getsize(tmp_path)
    if copied_size <= 0:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise ValueError(f"Copied file is empty: {src_path}")

    if os.path.exists(dest_path):
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return "exists"

    os.rename(tmp_path, dest_path)
    return "copied"

def sync_source_to_local_once():
    copied = 0
    skipped = 0
    error = None
    ensure_local_invoice_dirs()

    try:
        source_files = os.listdir(SOURCE_SHARE_PATH)
        update_status(source_share_available=True)
    except Exception as e:
        error = f"Source Share Error: {type(e).__name__}: {str(e)}"
        logger.warning(f"Invoice source sync waiting for share access: {error}")
        update_status(
            source_share_available=False,
            last_sync_at=datetime.now().isoformat(),
            last_sync_error=error,
            copied_count=0,
            skipped_count=0,
        )
        refresh_local_pdf_count()
        return {"copied": copied, "skipped": skipped, "error": error}

    for name in source_files:
        if not name.lower().endswith(".pdf"):
            continue
        src_path = os.path.join(SOURCE_SHARE_PATH, name)
        dest_path = os.path.join(LOCAL_INBOX_PATH, name)
        try:
            if not os.path.isfile(src_path):
                skipped += 1
                continue
            if same_file_already_copied(src_path, dest_path):
                skipped += 1
                continue
            if os.path.exists(dest_path):
                logger.warning(f"Local inbox already has a different PDF named {name}; skipping to avoid overwrite.")
                skipped += 1
                continue

            result = copy_pdf_to_local_inbox(src_path, dest_path)
            if result == "copied":
                copied += 1
                logger.info(f"Copied invoice PDF from source share to local inbox: {name}")
            else:
                skipped += 1
        except Exception as e:
            error = f"Copy Error for {name}: {type(e).__name__}: {str(e)}"
            logger.error(error)
            skipped += 1

    update_status(
        source_share_available=True,
        last_sync_at=datetime.now().isoformat(),
        last_sync_error=error,
        copied_count=copied,
        skipped_count=skipped,
    )
    refresh_local_pdf_count()
    return {"copied": copied, "skipped": skipped, "error": error}

def sync_source_to_local_loop():
    logger.info(
        f"Invoice source sync loop started. source={SOURCE_SHARE_PATH!r}, local_inbox={LOCAL_INBOX_PATH!r}"
    )
    update_status(sync_running=True)
    while True:
        try:
            result = sync_source_to_local_once()
            if result.get("error"):
                logger.info(f"Invoice source sync retry scheduled in {SYNC_INTERVAL_SECONDS}s")
            else:
                logger.info(
                    f"Invoice source sync complete. copied={result['copied']}, skipped={result['skipped']}"
                )
        except Exception as e:
            reason = f"Sync Loop Error: {type(e).__name__}: {str(e)}"
            logger.error(reason)
            update_status(last_sync_at=datetime.now().isoformat(), last_sync_error=reason)
            refresh_local_pdf_count()
        time.sleep(SYNC_INTERVAL_SECONDS)

def parse_pdf(file_path):
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
                    payment_reference = None # Initialize payment-level reference
                    extracted_date = None

                    # Try to extract reference from line first
                    ref_match = re.search(r"(?:Ref(?:erence)?|UTR|TxnID)\s*[:=]?\s*([A-Z0-9]+)", line, re.IGNORECASE)
                    if ref_match:
                        payment_reference = ref_match.group(1)

                    # Try to extract date from line (e.g. UPI 01/06/2026)
                    date_match = re.search(r"(\d{2}[-/]\d{2}[-/]\d{4})", line)
                    if date_match:
                        try:
                            extracted_date = datetime.strptime(date_match.group(1).replace("/", "-"), "%d-%m-%Y")
                        except: pass

                    # Determine mode
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
                    else: mode = "UNKNOWN" # Ensure mode is set if no keywords found

                    # Explicitly nullify payment_reference for non-electronic/cheque modes
                    if mode in ["CASH", "ADVANCE", "OLD_GOLD_EXCHANGE", "BALANCE", "UNKNOWN"]: # BALANCE and UNKNOWN also should not have references
                        payment_reference = None

                    if mode != "UNKNOWN":
                        payments.append({
                            "mode": mode,
                            "amount": amt,
                            "date": extracted_date, # Use extracted_date here
                            "raw": line.strip(),
                            "reference": payment_reference # Add extracted payment-level reference
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
        update_status(last_error=f"Parse Error ({os.path.basename(file_path)}): {str(e)}")
        return None

def process_invoice(file_path):
    if not file_path.lower().endswith(".pdf"):
        return

    update_status(last_file_seen=os.path.basename(file_path))
    
    file_hash = get_file_hash(file_path)
    if not file_hash:
        increment_status("failed_files")
        return

    db = SessionLocal()
    try:
        # 1. SHA256 Hash check
        existing_hash = db.query(Bill).filter(Bill.pdf_hash == file_hash).first()
        if existing_hash:
            logger.info(f"Duplicate hash detected for {os.path.basename(file_path)}")
            increment_status("skipped_duplicates")
            record_duplicate_result(handle_duplicate(file_path, db, reason="Duplicate PDF SHA256 hash", file_hash=file_hash))
            return

        invoice_data = parse_pdf(file_path)
        if not invoice_data or not invoice_data["bill_number"]:
            logger.warning(f"Parse Failed: {os.path.basename(file_path)} (No bill number)")
            increment_status("failed_files")
            from backend.email_notifier import send_red_alert_email
            send_red_alert_email(
                subject=f"RED ALERT: Parse Failure - {os.path.basename(file_path)}",
                body=f"System failed to parse invoice details from file: {file_path}"
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
            increment_status("skipped_duplicates")
            record_duplicate_result(handle_duplicate(file_path, db, reason="5-point identity match (Number, Date, Customer, Total)", file_hash=file_hash))
            return

        # Check for just number match (could be a mistake or update)
        duplicate_num = db.query(Bill).filter(Bill.bill_number == invoice_data["bill_number"]).first()
        if duplicate_num:
            logger.warning(f"Duplicate Number Skip: {invoice_data['bill_number']} (Partial identity match)")
            increment_status("skipped_duplicates")
            record_duplicate_result(handle_duplicate(file_path, db, reason="Duplicate Invoice Number match", file_hash=file_hash))
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
                utr_reference=None if p["mode"] in ["CASH", "ADVANCE", "OLD_GOLD_EXCHANGE", "CHEQUE"] else (new_bill.reference_no if p["mode"] == "BANK_TRANSFER" else p.get("reference")),
                cheque_number=p.get("reference") if p["mode"] == "CHEQUE" else None,
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
                body=f"Invoice {new_bill.bill_number} for {new_bill.customer_name} has a mismatch.\nBilled Total: {new_bill.total_amount}\nSum of Payments: {total_payments}"
            )

        db.commit()
        logger.info(f"Invoice Inserted: {new_bill.bill_number} from {os.path.basename(file_path)}")
        
        # TRIGGER RECONCILIATION RETRY for this new bill
        from backend.reconciliation.logic import reconcile_unreconciled_alerts
        reconcile_unreconciled_alerts(db)
        
        increment_status("invoices_inserted")
        update_status(last_processed_time=datetime.now().isoformat())

    except Exception as e:
        db.rollback()
        logger.error(f"Database Error processing {file_path}: {e}")
        update_status(last_error=f"DB Error: {str(e)}")
        increment_status("failed_files")
    finally:
        increment_status("files_processed")
        db.close()

def perform_scan():
    if not check_share_health():
        return
    
    logger.info(f"Folder scan started: {WATCH_PATH!r}")
    exists = os.path.exists(WATCH_PATH)
    logger.info(f"os.path.exists(WATCH_PATH): {exists}")
    
    try:
        all_files = os.listdir(WATCH_PATH)
        logger.info(f"os.listdir count: {len(all_files)}")
        logger.info(f"First 5 files: {all_files[:5]}")
        
        pdf_files = [f for f in all_files if f.lower().endswith(".pdf")]
        logger.info(f"PDF files count: {len(pdf_files)}")
        
        update_status(pdf_files_found=len(pdf_files), path_exists=True)
        
        for file in pdf_files:
            process_invoice(os.path.join(WATCH_PATH, file))
        
        logger.info(f"Folder scan complete. Total files in folder: {len(all_files)}.")
    except Exception as e:
        logger.error(f"Error scanning folder {WATCH_PATH}: {e}")
        update_status(last_error=f"Scan Error: {str(e)}")
        # Keep watcher_running True if path exists as per instructions
        update_status(path_exists=os.path.exists(WATCH_PATH))


class InvoiceHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".pdf"):
            process_invoice(event.src_path)
    def on_modified(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".pdf"):
            process_invoice(event.src_path)

def start_watcher():
    logger.info(f"start_watcher invoked. WATCH_PATH={WATCH_PATH!r}")
    ensure_local_invoice_dirs()
    update_status(
        active_watch_path=WATCH_PATH,
        watcher_path=WATCH_PATH,
        watcher_running=False,
        observer_started=False,
        watcher_mode="starting",
        observer_error=None,
    )

    observer = None
    if check_share_health():
        event_handler = InvoiceHandler()
        observer = Observer()
        try:
            observer.schedule(event_handler, WATCH_PATH, recursive=False)
            observer.start()
            update_status(
                watcher_running=True,
                observer_started=True,
                watcher_mode="observer",
                observer_error=None,
            )
            logger.info(f"Realtime watcher active on {WATCH_PATH}")
        except Exception as e:
            reason = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Realtime watcher observer failed on {WATCH_PATH}: {reason}")
            update_status(
                watcher_running=True,
                observer_started=False,
                watcher_mode="polling",
                observer_error=reason,
                last_error=f"Observer Error: {reason}; polling active",
            )
            observer = None
    else:
        update_status(watcher_running=False, observer_started=False, watcher_mode="offline")

    try:
        while True:
            time.sleep(60) # Re-verify entire list of pdfs in the folder every minute
            if check_share_health():
                if ingestion_status["watcher_mode"] == "offline":
                    logger.info("Invoice share re-connected.")
                if not ingestion_status["observer_started"]:
                    update_status(watcher_running=True, watcher_mode="polling")
                else:
                    update_status(watcher_running=True, watcher_mode="observer")
                # Periodic scan to ensure nothing was missed by watcher
                perform_scan()
            else:
                update_status(watcher_running=False, observer_started=False, watcher_mode="offline")
    except Exception as e:
        logger.error(f"Watcher thread crashed: {e}")
        update_status(watcher_running=False, last_error=f"Watcher Crash: {str(e)}")

def start_ingestion_thread():
    global sync_thread_started, watcher_thread_started

    ensure_local_invoice_dirs()
    refresh_local_pdf_count()

    with thread_state_lock:
        if not sync_thread_started:
            sync_thread = threading.Thread(target=sync_source_to_local_loop, daemon=True)
            sync_thread.start()
            sync_thread_started = True

        # Run one scan immediately against the local inbox so existing local PDFs
        # are available even when the PC2 share is temporarily unavailable.
        scan_thread = threading.Thread(target=perform_scan, daemon=True)
        scan_thread.start()

        if not watcher_thread_started:
            watcher_thread = threading.Thread(target=start_watcher, daemon=True)
            watcher_thread.start()
            watcher_thread_started = True

if __name__ == "__main__":
    ensure_local_invoice_dirs()
    sync_source_to_local_once()
    perform_scan()
    start_watcher()
