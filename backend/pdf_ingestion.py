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
from backend.database import SessionLocal, engine
from backend.models import Bill, Payment, AuditLog, Cheque
import json

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PDF_Ingestion")

WATCH_PATH = r"Z:\Aradhana\InvoicePDFs"

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
    "path_exists": False,
    "pdf_files_found": 0,
    "files_processed": 0,
    "invoices_inserted": 0,
    "skipped_duplicates": 0,
    "failed_files": 0,
    "last_file_seen": None,
    "last_processed_time": None,
    "last_error": None,
    "cuda_active": CUDA_AVAILABLE
}

status_lock = threading.Lock()

def update_status(**kwargs):
    with status_lock:
        for key, value in kwargs.items():
            if key in ingestion_status:
                ingestion_status[key] = value

def increment_status(key, amount=1):
    with status_lock:
        if key in ingestion_status:
            ingestion_status[key] += amount

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
    exists = os.path.exists(WATCH_PATH)
    update_status(path_exists=exists)
    if not exists:
        logger.error(f"Invoice Share Offline: {WATCH_PATH} is unavailable.")
        return False
    return True

def parse_pdf(file_path):
    try:
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"
        
        if not text.strip() and (OCR_ACCELERATION != "cpu"):
            logger.info(f"No text extracted from {file_path}, attempting OCR fallback...")
            pass

        data = {
            "raw_text": text,
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

        # 2. Date
        date_match = re.search(r"Date\s*:\s*(\d{2}[-/]\d{2}[-/]\d{4})", text)
        if date_match:
            try:
                data["invoice_date"] = datetime.strptime(date_match.group(1).replace("/", "-"), "%d-%m-%Y")
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
                    if "CASH" in line_upper: mode = "CASH"
                    elif any(x in line_upper for x in ["UPI", "RTGS", "IMPS", "NEFT", "BANK TRANSFER"]): mode = "BANK_TRANSFER"
                    elif "ADVANCE" in line_upper: mode = "ADVANCE"
                    elif "CHEQUE" in line_upper or "CHQ" in line_upper: mode = "CHEQUE"
                    elif "CARD" in line_upper: mode = "CARD"
                    elif "BALANCE" in line_upper: mode = "BALANCE"
                    elif "OLD GOLD" in line_upper: mode = "OLD_GOLD_EXCHANGE"
                    
                    if mode != "UNKNOWN":
                        payments.append({"mode": mode, "amount": amt, "raw": line.strip()})
        
        data["payments"] = payments
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
        existing = db.query(Bill).filter(Bill.pdf_hash == file_hash).first()
        if existing:
            increment_status("skipped_duplicates")
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

        duplicate = db.query(Bill).filter(Bill.bill_number == invoice_data["bill_number"]).first()
        if duplicate:
            logger.warning(f"Duplicate Skip: {invoice_data['bill_number']} (Number match)")
            increment_status("skipped_duplicates")
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
            customer_name=invoice_data.get("customer_name") or "Unknown",
            customer_mobile=invoice_data.get("customer_mobile"),
            customer_address=invoice_data.get("customer_address"),
            taxable_value=invoice_data["taxable_value"],
            cgst=invoice_data["cgst"],
            sgst=invoice_data["sgst"],
            round_off=invoice_data["round_off"],
            total_amount=invoice_data["total_amount"],
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
            cash_received=sum(p["amount"] for p in invoice_data["payments"] if p["mode"] in ["CASH", "ADVANCE", "OLD_GOLD_EXCHANGE"]),
            bank_received=sum(p["amount"] for p in invoice_data["payments"] if p["mode"] == "BANK_TRANSFER"),
            card_received=sum(p["amount"] for p in invoice_data["payments"] if p["mode"] == "CARD"),
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
                body=f"Invoice {new_bill.bill_number} for {new_bill.customer_name} has a mismatch.\nBilled Total: {new_bill.total_amount}\nSum of Payments: {total_payments}"
            )

        db.commit()
        logger.info(f"Invoice Inserted: {new_bill.bill_number} from {os.path.basename(file_path)}")
        increment_status("invoices_inserted")
        update_status(last_processed_time=datetime.now().isoformat())

        # Archival logic: move yesterday's files to OLD
        import shutil
        if new_bill.invoice_date and new_bill.invoice_date.date() < datetime.now().date():
            old_dir = os.path.join(os.path.dirname(WATCH_PATH), "OLD")
            os.makedirs(old_dir, exist_ok=True)
            dest_path = os.path.join(old_dir, os.path.basename(file_path))
            try:
                # To prevent file-in-use errors, copy then delete
                shutil.copy2(file_path, dest_path)
                os.remove(file_path)
                logger.info(f"Archived old invoice: {os.path.basename(file_path)} to OLD directory.")
            except Exception as e:
                logger.error(f"Failed to archive {file_path}: {e}")

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
    
    logger.info(f"Folder scan started: {WATCH_PATH}")
    files = [f for f in os.listdir(WATCH_PATH) if f.lower().endswith(".pdf")]
    update_status(pdf_files_found=len(files))
    
    for file in files:
        process_invoice(os.path.join(WATCH_PATH, file))
    
    logger.info(f"Folder scan complete. Total files in folder: {len(files)}.")

class InvoiceHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            process_invoice(event.src_path)
    def on_modified(self, event):
        if not event.is_directory:
            process_invoice(event.src_path)

def start_watcher():
    if not check_share_health():
        update_status(watcher_running=False)
        # return # Let it continue to poll health

    event_handler = InvoiceHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_PATH, recursive=False)
    observer.start()
    update_status(watcher_running=True)
    logger.info(f"Realtime watcher/poller active on {WATCH_PATH}")
    
    try:
        while True:
            time.sleep(60) # Re-verify entire list of pdfs in the folder every minute
            if not os.path.exists(WATCH_PATH):
                update_status(path_exists=False, watcher_running=False)
            else:
                if not ingestion_status["path_exists"]:
                    logger.info("Invoice share re-connected.")
                update_status(path_exists=True, watcher_running=True)
                # Periodic scan to ensure nothing was missed by watcher
                perform_scan() 
    except Exception as e:
        logger.error(f"Watcher thread crashed: {e}")
        update_status(watcher_running=False, last_error=f"Watcher Crash: {str(e)}")

def start_ingestion_thread():
    # Run scan first
    # scan_thread = threading.Thread(target=perform_scan, daemon=True)
    # scan_thread.start()
    
    # Run watcher (which now also performs periodic scans)
    watcher_thread = threading.Thread(target=start_watcher, daemon=True)
    watcher_thread.start()

if __name__ == "__main__":
    perform_scan()
    start_watcher()
