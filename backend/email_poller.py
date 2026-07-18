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
from backend.database import get_session_factory
from backend import business_registry
from backend.models import BankAlert, Bill, AuditLog, Payment, Cheque, SMSAlert, SystemSetting
from backend.sms_parser import parse_bank_sms
import json
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("Email_Poller")

# Was hardcoded to "info@aradhanajewellers.com" — one specific business's
# own forwarding address, baked into the SMS-forwarder detection rule for
# every tenant. SMS_FORWARDER_SENDER lets a deployment configure its own
# (this module is still single-tenant/default-DB scoped until the
# background pollers are converted to loop over every business — see
# database.py's _default_slug docstring); falls back to relying on the
# "[SMSForwarder]" subject tag alone when unset, which still works without
# any hardcoded business identity.
SMS_FORWARDER_SENDER = os.environ.get("SMS_FORWARDER_SENDER", "")

# Was hardcoded to "shreearadhana1001@gmail.com" — see SMS_FORWARDER_SENDER
# above for the same fix applied to the bank-alert-forwarding rule.
BANK_ALERT_FORWARDER = os.environ.get("BANK_ALERT_FORWARDER", "")

# Per-tenant status trackers — see pdf_ingestion.py's equivalent comment
# for why this stopped being one shared global dict.
_email_status: dict[str, dict] = {}
status_lock = threading.Lock()


def _email_status_for(slug: str) -> dict:
    with status_lock:
        if slug not in _email_status:
            _email_status[slug] = {
                "last_sync": None,
                "next_sync": None,
                "events_found": 0,
                "last_error": None,
                "is_running": False,
            }
        return _email_status[slug]


def update_email_status(slug: str, **kwargs):
    st = _email_status_for(slug)
    with status_lock:
        for key, value in kwargs.items():
            if key in st:
                st[key] = value


def _tenant_imap_config(slug: str) -> dict:
    """Each business's own IMAP mailbox config from its profile, falling
    back to the shared env vars (a single deployment-wide mailbox) if that
    tenant hasn't configured its own — same convenience fallback used
    throughout this conversion."""
    profile = business_registry.load_profile(slug)
    imap = (profile or {}).get("imap") or {}
    return {
        "server": imap.get("server") or os.getenv("IMAP_SERVER") or os.getenv("IMAP_HOST") or os.getenv("BANK_IMAP_HOST"),
        "user": imap.get("user") or os.getenv("IMAP_USER") or os.getenv("BANK_IMAP_USERNAME"),
        "password": imap.get("password") or os.getenv("IMAP_PASSWORD") or os.getenv("BANK_IMAP_PASSWORD"),
        "folder": imap.get("folder") or os.getenv("IMAP_FOLDER", "INBOX"),
        "port": int(imap.get("port") or os.getenv("IMAP_PORT") or os.getenv("BANK_IMAP_PORT") or 993),
    }

def get_checkpoint(db: Session):
    setting = db.query(SystemSetting).filter(SystemSetting.key == "last_email_checkpoint").first()
    if setting:
        try:
            return datetime.fromisoformat(setting.value)
        except:
            pass

    # Default: Today's shop opening
    now = datetime.now()
    default_open = now.replace(hour=10, minute=0, second=0, microsecond=0)
    if now.weekday() == 3: # Thursday
        default_open = now.replace(hour=12, minute=0, second=0, microsecond=0)

    return default_open

def save_checkpoint(db: Session, last_ts: datetime):
    now = datetime.now()
    if last_ts > now:
        logger.warning(f"FUTURE CHECKPOINT DETECTED: {last_ts}. System time: {now}. Clamping to current time.")
        last_ts = now
        
    setting = db.query(SystemSetting).filter(SystemSetting.key == "last_email_checkpoint").first()
    if not setting:
        setting = SystemSetting(key="last_email_checkpoint", value=last_ts.isoformat())
        db.add(setting)
    else:
        try:
            current = datetime.fromisoformat(setting.value)
        except:
            current = datetime.min
            
        if last_ts > current:
            setting.value = last_ts.isoformat()
    db.commit()

def parse_email_event(subject, body):
    if "[SMSForwarder]" in subject:
        return "sms_forwarded"
        
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

def fetch_real_emails(since_date: datetime, slug: str):
    cfg = _tenant_imap_config(slug)
    imap_server, imap_user, imap_pass = cfg["server"], cfg["user"], cfg["password"]
    imap_folder, imap_port = cfg["folder"], cfg["port"]

    if not imap_server or not imap_user or not imap_pass:
        logger.warning(f"[{slug}] IMAP credentials not configured. Skipping real email fetch.")
        return []

    emails_list = []
    try:
        mail = imaplib.IMAP4_SSL(imap_server, port=imap_port)
        mail.login(imap_user, imap_pass)
        mail.select(imap_folder)

        # Search SINCE date (granularity is Day)
        date_str = since_date.strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{date_str}")')
        
        if status == "OK" and messages[0]:
            msg_nums = messages[0].split()
            if msg_nums:
                # Fetch only new ones - this is still simple, but limit to last 200 for each cycle
                # to prevent long hangs.
                chunk = msg_nums[-200:]
                fetch_ids = b",".join(chunk)
                typ, data = mail.fetch(fetch_ids, "(RFC822)")
                for response_part in data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        message_id = msg.get("Message-ID")
                        subject = get_decoded_header(msg.get("Subject"))
                        sender = get_decoded_header(msg.get("From"))
                        date_tuple = email.utils.parsedate_tz(msg.get("Date"))
                        if date_tuple:
                            local_date = datetime.fromtimestamp(email.utils.mktime_tz(date_tuple))
                        else:
                            local_date = datetime.now()
                            
                        # Filter by exact time checkpoint
                        if local_date <= since_date:
                            continue

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
                        
                        emails_list.append({
                            "message_id": message_id,
                            "subject": subject,
                            "sender": sender,
                            "date": local_date,
                            "body": " ".join(body.split())
                        })
        mail.logout()
    except Exception as e:
        logger.error(f"[{slug}] IMAP Fetch Error: {e}")
        update_email_status(slug, last_error=f"IMAP Error: {str(e)}")
    return emails_list

from backend.email_parser import parse_bank_email
from backend.schemas import RawEmail

def process_emails(slug: str):
    logger.info(f"[{slug}] Polling bank emails via IMAP...")
    update_email_status(slug, is_running=True)

    db = get_session_factory(slug)()
    events_found = 0
    try:
        checkpoint = get_checkpoint(db)
        logger.info(f"[{slug}] Using checkpoint: {checkpoint}")

        real_emails = fetch_real_emails(checkpoint, slug)
        logger.info(f"[{slug}] Fetched {len(real_emails)} emails since checkpoint.")
        
        newest_ts = checkpoint
        for email_data in real_emails:
            sender = email_data["sender"].lower()
            subject = email_data["subject"]
            body = email_data["body"]
            received_at = email_data["date"]
            
            if received_at > newest_ts:
                newest_ts = received_at
            
            logger.info(f"Processing Email: From={sender}, Subject={subject}, Date={received_at}")

            # --- Classification Rules ---
            
            # Rule 3: Google security emails
            if "no-reply@accounts.google.com" in sender:
                logger.info(f"Skipping Google security email from {sender}")
                continue
                
            # Rule 4: Promotional emails (simple heuristic)
            if any(promo in subject.lower() for promo in ["offer", "discount", "sale", "promotional", "newsletter"]):
                logger.info(f"Skipping promotional email: {subject}")
                continue

            # Rule 1: SMS Forwarder
            is_sms_forwarder = (bool(SMS_FORWARDER_SENDER) and SMS_FORWARDER_SENDER in sender) or "[SMSForwarder]" in subject
            
            if is_sms_forwarder:
                logger.info(f"Classified as SMS_FORWARDER: {subject}")
                parsed_sms = parse_bank_sms(body)
                if not parsed_sms.amount or parsed_sms.amount <= 0:
                    logger.warning(f"SMSForwarder skip: No amount found or amount <= 0. Body: {body[:100]}...")
                    continue
                
                exists = db.query(SMSAlert).filter(SMSAlert.email_message_id == email_data["message_id"]).first()
                if not exists and parsed_sms.utr_reference:
                    exists = db.query(SMSAlert).filter(SMSAlert.utr_reference == parsed_sms.utr_reference).first()
                    
                if exists:
                    logger.info(f"SMSAlert duplicate skipped: {parsed_sms.utr_reference or email_data['message_id']}")
                    continue

                sms_sender = "UNKNOWN"
                sender_match = re.search(r"From\s*:\s*([A-Za-z0-9-]+)", body)
                if sender_match:
                    sms_sender = sender_match.group(1)
                    
                ts = received_at
                if parsed_sms.transaction_date:
                    try:
                        ts = datetime.fromisoformat(parsed_sms.transaction_date)
                    except:
                        try:
                            ts = datetime.strptime(parsed_sms.transaction_date, "%Y-%m-%d %H:%M:%S")
                        except:
                            pass

                new_sms = SMSAlert(
                    sender=sms_sender,
                    transaction_timestamp=ts,
                    bank_name=parsed_sms.sender_bank or "ICICI",
                    account_suffix=parsed_sms.account_suffix,
                    credit_or_debit="CREDIT", 
                    amount=parsed_sms.amount,
                    utr_reference=parsed_sms.utr_reference,
                    payer_name=parsed_sms.payer_name,
                    raw_body=body,
                    email_message_id=email_data["message_id"],
                    parsed_confidence=1.0 if parsed_sms.confidence == "HIGH" else 0.5
                )
                db.add(new_sms)
                db.flush()
                
                utr_to_use = new_sms.utr_reference if new_sms.utr_reference else f"SMS_{email_data['message_id']}"
                
                # Deduplicate BankAlert as well
                exists_alert = db.query(BankAlert).filter(BankAlert.utr_reference == utr_to_use).first()
                if not exists_alert:
                    alert = BankAlert(
                        bank_name=new_sms.bank_name,
                        amount=new_sms.amount,
                        utr_reference=utr_to_use,
                        sender=new_sms.sender,
                        received_at=new_sms.transaction_timestamp,
                        raw_text=f"SMS Forwarded via Email: {body}"
                    )
                    db.add(alert)
                    db.flush()
                    events_found += 1
                    
                    from backend.reconciliation.logic import verify_payment_event
                    verify_payment_event(db, alert, source="SMS_FORWARDER")
                    logger.info(f"Successfully processed SMS_FORWARDER: {alert.utr_reference}, Amount={alert.amount}")
                else:
                    logger.info(f"BankAlert duplicate (from SMS): {utr_to_use} already exists.")
                continue

            # Rule 2: Bank Email Alerts (forwarded from a business's own
            # bank-alert forwarding address — was hardcoded to one specific
            # business's Gmail; BANK_ALERT_FORWARDER lets a deployment
            # configure its own, same pattern as SMS_FORWARDER_SENDER above)
            is_forwarded_bank = bool(BANK_ALERT_FORWARDER) and BANK_ALERT_FORWARDER in sender
            is_direct_bank = any(bank in (sender + subject).lower() for bank in ["icici", "hdfc", "sbi", "axis", "kotak"])
            
            if is_forwarded_bank or is_direct_bank:
                logger.info(f"Classified as BANK_EMAIL: {subject} (Forwarded={is_forwarded_bank})")
                parsed_email = parse_bank_email(subject, body)
                
                if not parsed_email.amount or parsed_email.amount <= 0:
                    logger.warning(f"Bank email skip: No amount found. Subject={subject}")
                    continue
                
                dedupe_key = parsed_email.utr_reference if parsed_email.utr_reference else f"SYNC_{received_at.timestamp()}_{parsed_email.amount}"
                
                exists = db.query(BankAlert).filter(BankAlert.utr_reference == dedupe_key).first()
                if exists:
                    logger.info(f"BankAlert duplicate skipped: {dedupe_key}")
                    continue
                    
                alert = BankAlert(
                    bank_name=parsed_email.sender_bank or "IMAP_BANK",
                    amount=parsed_email.amount,
                    utr_reference=dedupe_key,
                    sender=email_data["sender"],
                    received_at=received_at,
                    raw_text=f"Subject: {subject}\nBody: {body}"
                )
                db.add(alert)
                db.flush()
                events_found += 1
                
                from backend.reconciliation.logic import verify_payment_event
                verify_payment_event(db, alert, source="EMAIL")
                logger.info(f"Successfully processed BANK_EMAIL: {alert.utr_reference}, Amount={alert.amount}")
                continue
            
            logger.info(f"Email skipped: No matching classification for {sender} / {subject}")

        if newest_ts > checkpoint:
            save_checkpoint(db, newest_ts)

        # RETRY RECONCILIATION FOR UNRECONCILED ALERTS
        from backend.reconciliation.logic import reconcile_unreconciled_alerts
        reconcile_unreconciled_alerts(db)

        db.commit()
        update_email_status(
            slug,
            last_sync=datetime.now().isoformat(),
            next_sync=(datetime.now().timestamp() + 300),
            events_found=events_found
        )
    except Exception as e:
        db.rollback()
        logger.error(f"[{slug}] Email Polling Error: {e}")
        update_email_status(slug, last_error=str(e))
    finally:
        db.close()
        update_email_status(slug, is_running=False)

def start_email_poller():
    """Spawns one polling loop thread PER registered business — used to
    spawn exactly one loop against one shared default-tenant session. New
    businesses onboarded after this runs need a process restart to pick up
    polling, same as pdf_ingestion.py's equivalent."""
    def run(slug):
        while True:
            process_emails(slug)
            time.sleep(300)

    for slug in business_registry.list_businesses():
        thread = threading.Thread(target=run, args=(slug,), daemon=True)
        thread.start()
        logger.info(f"[{slug}] Email poller thread started.")
