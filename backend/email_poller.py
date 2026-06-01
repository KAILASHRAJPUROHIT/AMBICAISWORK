import os
import time
import logging
import threading
import re
import imaplib
import email
import hashlib
from email.header import decode_header
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models import BankAlert, Bill, AuditLog, Payment, Cheque
import json
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("Email_Poller")

email_status = {
    "last_sync": None,
    "next_sync": None,
    "events_found": 0,
    "last_error": None,
    "is_running": False
}

status_lock = threading.Lock()

def update_email_status(**kwargs):
    with status_lock:
        for key, value in kwargs.items():
            if key in email_status:
                email_status[key] = value

def parse_email_event(subject, body):
    content = (subject + " " + body).lower()
    
    event_type = "unknown"
    if "credited" in content or "received" in content:
        event_type = "credited"
        if "neft" in content: event_type = "neft_received"
        elif "imps" in content: event_type = "imps_received"
        elif "rtgs" in content: event_type = "rtgs_received"
        elif "upi" in content: event_type = "upi_received"
    elif "deposited" in content and "cheque" in content:
        event_type = "cheque_deposited"
    elif "cleared" in content and "cheque" in content:
        event_type = "cheque_cleared"
    elif "bounced" in content or "returned" in content:
        if "cheque" in content:
            event_type = "cheque_bounced" if "bounced" in content else "cheque_returned"
    elif "debit" in content:
        event_type = "debit"
    elif "reversal" in content:
        event_type = "reversal"
        
    return event_type

def get_decoded_header(header_value):
    if not header_value: return ""
    decoded_list = decode_header(header_value)
    header_str = ""
    for (decoded_string, charset) in decoded_list:
        if isinstance(decoded_string, bytes):
            try:
                header_str += decoded_string.decode(charset or "utf-8", errors="ignore")
            except:
                header_str += decoded_string.decode("utf-8", errors="ignore")
        else:
            header_str += str(decoded_string)
    return header_str

def strip_html(text):
    return re.sub(r'<[^>]+>', ' ', text)

def fetch_real_emails():
    imap_server = os.getenv("IMAP_SERVER") or os.getenv("IMAP_HOST") or os.getenv("BANK_IMAP_HOST")
    imap_user = os.getenv("IMAP_USER") or os.getenv("BANK_IMAP_USERNAME")
    imap_pass = os.getenv("IMAP_PASSWORD") or os.getenv("BANK_IMAP_PASSWORD")
    imap_folder = os.getenv("IMAP_FOLDER", "INBOX")
    imap_port = int(os.getenv("IMAP_PORT") or os.getenv("BANK_IMAP_PORT") or 993)

    if not imap_server or not imap_user or not imap_pass:
        logger.warning("IMAP credentials not fully configured in .env. Skipping real email fetch.")
        return []

    emails = []
    try:
        mail = imaplib.IMAP4_SSL(imap_server, port=imap_port)
        mail.login(imap_user, imap_pass)
        mail.select(imap_folder)

        # Search for emails from the last 30 days
        date_since = (datetime.now() - timedelta(days=30)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{date_since}")')
        
        if status == "OK" and messages[0]:
            msg_nums = messages[0].split()
            if msg_nums:
                # Fetch in chunks of 200
                chunk_size = 200
                for i in range(0, len(msg_nums), chunk_size):
                    chunk = msg_nums[i:i + chunk_size]
                    fetch_ids = b",".join(chunk)
                    typ, data = mail.fetch(fetch_ids, "(RFC822)")
                    for response_part in data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            
                            subject = get_decoded_header(msg.get("Subject"))
                            sender = get_decoded_header(msg.get("From"))
                            date_tuple = email.utils.parsedate_tz(msg.get("Date"))
                            if date_tuple:
                                local_date = datetime.fromtimestamp(email.utils.mktime_tz(date_tuple))
                            else:
                                local_date = datetime.now()
                            
                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    content_type = part.get_content_type()
                                    if content_type in ["text/plain", "text/html"]:
                                        try:
                                            part_body = part.get_payload(decode=True).decode(errors="ignore")
                                            if content_type == "text/html":
                                                part_body = strip_html(part_body)
                                            body += " " + part_body
                                        except:
                                            pass
                            else:
                                try:
                                    body = msg.get_payload(decode=True).decode(errors="ignore")
                                    if msg.get_content_type() == "text/html":
                                        body = strip_html(body)
                                except:
                                    pass
                            
                            emails.append({
                                "subject": subject,
                                "sender": sender,
                                "date": local_date,
                                "body": " ".join(body.split())
                            })
        mail.logout()
    except Exception as e:
        logger.error(f"IMAP Fetch Error: {e}")
        update_email_status(last_error=f"IMAP Error: {str(e)}")
    return emails

def process_emails():
    """
    Fetches emails securely from the configured IMAP server, 
    parses bank alert notifications, and updates the database using multi-point verification.
    """
    logger.info("Polling bank emails via IMAP...")
    update_email_status(is_running=True)
    
    db = SessionLocal()
    events_found = 0
    try:
        real_emails = fetch_real_emails()
        
        for email_data in real_emails:
            body = email_data["body"]
            event_type = parse_email_event(email_data["subject"], body)
            
            # Extract amount
            amt_match = re.search(r"(?:INR|RS\.?)\s*([\d,]+\.\d{2})", body, re.IGNORECASE)
            amount = float(amt_match.group(1).replace(",", "")) if amt_match else 0.0
            
            if amount <= 0: continue
            
            # Extract UTR
            utr_match = re.search(r"Ref:\s*([A-Z0-9/]+)", body, re.IGNORECASE)
            if not utr_match:
                utr_match = re.search(r"UTR[:\s]*([A-Z0-9]+)", body, re.IGNORECASE)
                
            utr = utr_match.group(1) if utr_match else None
            
            # Generate synthetic UTR if none exists to prevent duplicate insertion
            dedupe_key = utr if utr else f"SYNC_{email_data['date'].timestamp()}_{amount}"
            
            # Store BankAlert
            exists = db.query(BankAlert).filter(BankAlert.utr_reference == dedupe_key).first()
            if not exists:
                alert = BankAlert(
                    bank_name="IMAP_BANK",
                    amount=amount,
                    utr_reference=dedupe_key,
                    sender=email_data["sender"],
                    received_at=email_data["date"],
                    raw_text=f"Subject: {email_data['subject']}\nBody: {body}"
                )
                db.add(alert)
                db.flush()
                events_found += 1
                
                # RECONCILIATION LOGIC (Centralized)
                from backend.reconciliation.logic import verify_payment_event
                verify_payment_event(db, alert, source="EMAIL")
                
                # CHEQUE LOGIC
                if event_type == "cheque_cleared":
                    # Find cheque
                    cheque = db.query(Cheque).filter(Cheque.amount == amount, Cheque.status == "Blue").first()
                    if cheque:
                        cheque.status = "Green"
                        cheque.cleared_at = datetime.now()
                        # Update Bill/Payment
                        bill = db.query(Bill).filter(Bill.id == cheque.bill_id).first()
                        if bill:
                            bill.status = "Green"
                            bill.status_text = "Cleared (Cheque Cleared)"
                            bill.review_required = 0
                elif event_type in ["cheque_bounced", "cheque_returned"]:
                    cheque = db.query(Cheque).filter(Cheque.amount == amount, Cheque.status == "Blue").first()
                    if cheque:
                        cheque.status = "Red"
                        cheque.return_reason = event_type.upper()
                        bill = db.query(Bill).filter(Bill.id == cheque.bill_id).first()
                        if bill:
                            bill.status = "Red"
                            bill.status_text = f"Error: {event_type.upper()}"
                            bill.review_required = 1

        db.commit()
        update_email_status(
            last_sync=datetime.now().isoformat(),
            next_sync=(datetime.now().timestamp() + 300),
            events_found=events_found
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Email Polling Error: {e}")
        update_email_status(last_error=str(e))
    finally:
        db.close()
        update_email_status(is_running=False)

def start_email_poller():
    def run():
        while True:
            process_emails()
            time.sleep(300) # 5 minutes
            
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info("Email poller thread started.")
