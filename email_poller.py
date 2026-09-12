# Trimmed from payment-auditor/backend/email_poller.py. Two things removed
# on purpose, not by accident:
#   1. The "Rule 2: Bank Email Alerts" branch, which wrote BankAlert rows and
#      fed the reconciliation engine — /api/bank-activity never reads
#      BankAlert, only SMSAlert, so that branch has no observable effect here.
#   2. Every call into backend.reconciliation.logic (verify_payment_event,
#      reconcile_unreconciled_alerts) — that engine doesn't exist in this
#      service and was never part of what the notifier displays.
# The SMS-forwarder path (the one that actually writes SMSAlert) is kept
# as-is, including its classification rules.
import os
import time
import logging
import threading
import re
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from database import SessionLocal
from models import SMSAlert
from sms_parser import detect_credit_or_debit, parse_bank_sms
from dotenv import load_dotenv

load_dotenv()

# The business runs on IST. This service is hosted on a cloud box whose
# system clock is UTC (unlike the original on-prem Billing PC, where
# datetime.now() naturally returned IST wall time) - every "now"/checkpoint
# here needs to be computed in IST explicitly, or a UTC host clock silently
# shifts every comparison by 5:30 and business-hours logic breaks (e.g. the
# 10 AM checkpoint default becomes 3:30 PM IST, and every email sent before
# that gets treated as already-seen and skipped). India has no DST, so a
# fixed offset is correct year-round - no tzdata package needed.
IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    """Current IST wall-clock time as a naive datetime, matching the naive
    (no-tzinfo) convention used for every timestamp already stored here."""
    return datetime.now(IST).replace(tzinfo=None)

EMAIL_POLL_INTERVAL_SECONDS = max(1, int(os.getenv("EMAIL_POLL_INTERVAL_SECONDS", "5")))

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


def _system_setting_get(db: Session, key: str):
    from models import SystemSetting
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return setting.value if setting else None


def _system_setting_set(db: Session, key: str, value: str):
    from models import SystemSetting
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting:
        setting.value = value
    else:
        db.add(SystemSetting(key=key, value=value))


def get_checkpoint(db: Session):
    value = _system_setting_get(db, "last_email_checkpoint")
    if value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    now = now_ist()
    default_open = now.replace(hour=10, minute=0, second=0, microsecond=0)
    if now.weekday() == 3:  # Thursday
        default_open = now.replace(hour=12, minute=0, second=0, microsecond=0)
    return default_open


def save_checkpoint(db: Session, last_ts: datetime):
    now = now_ist()
    if last_ts > now:
        logger.warning(f"FUTURE CHECKPOINT DETECTED: {last_ts}. System time: {now}. Clamping to current time.")
        last_ts = now
    current_raw = _system_setting_get(db, "last_email_checkpoint")
    try:
        current = datetime.fromisoformat(current_raw) if current_raw else datetime.min
    except ValueError:
        current = datetime.min
    if last_ts > current:
        _system_setting_set(db, "last_email_checkpoint", last_ts.isoformat())
    db.commit()


def get_decoded_header(header_value):
    if not header_value:
        return ""
    decoded_list = decode_header(header_value)
    header_str = ""
    for decoded_string, charset in decoded_list:
        if isinstance(decoded_string, bytes):
            try:
                header_str += decoded_string.decode(charset or "utf-8", errors="ignore")
            except Exception:
                header_str += decoded_string.decode("utf-8", errors="ignore")
        else:
            header_str += str(decoded_string)
    return header_str


def strip_html(text):
    return re.sub(r'<[^>]+>', ' ', text)


def fetch_real_emails(since_date: datetime):
    imap_server = os.getenv("IMAP_SERVER") or os.getenv("IMAP_HOST") or os.getenv("BANK_IMAP_HOST")
    imap_user = os.getenv("IMAP_USER") or os.getenv("BANK_IMAP_USERNAME")
    imap_pass = os.getenv("IMAP_PASSWORD") or os.getenv("BANK_IMAP_PASSWORD")
    imap_folder = os.getenv("IMAP_FOLDER", "INBOX")
    imap_port = int(os.getenv("IMAP_PORT") or os.getenv("BANK_IMAP_PORT") or 993)

    if not imap_server or not imap_user or not imap_pass:
        logger.warning("IMAP credentials not fully configured. Skipping email fetch.")
        return []

    emails_list = []
    try:
        mail = imaplib.IMAP4_SSL(imap_server, port=imap_port)
        mail.login(imap_user, imap_pass)
        mail.select(imap_folder)

        date_str = since_date.strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{date_str}")')

        if status == "OK" and messages[0]:
            msg_nums = messages[0].split()
            if msg_nums:
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
                            # mktime_tz gives a correct epoch regardless of
                            # the email's own timezone; convert that to IST
                            # explicitly rather than via fromtimestamp()'s
                            # host-local interpretation (UTC on this box).
                            local_date = datetime.fromtimestamp(email.utils.mktime_tz(date_tuple), tz=IST).replace(tzinfo=None)
                        else:
                            local_date = now_ist()

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
                                    except Exception:
                                        pass
                        else:
                            try:
                                body = msg.get_payload(decode=True).decode(errors="ignore")
                                if msg.get_content_type() == "text/html":
                                    body = strip_html(body)
                            except Exception:
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
        logger.error(f"IMAP Fetch Error: {e}")
        update_email_status(last_error=f"IMAP Error: {str(e)}")
    return emails_list


def process_emails():
    logger.info("Polling bank emails via IMAP...")
    update_email_status(is_running=True)

    db = SessionLocal()
    events_found = 0
    try:
        checkpoint = get_checkpoint(db)
        logger.info(f"Using checkpoint: {checkpoint}")

        real_emails = fetch_real_emails(checkpoint)
        logger.info(f"Fetched {len(real_emails)} emails since checkpoint.")

        newest_ts = checkpoint
        for email_data in real_emails:
            sender = email_data["sender"].lower()
            subject = email_data["subject"]
            body = email_data["body"]
            received_at = email_data["date"]

            if received_at > newest_ts:
                newest_ts = received_at

            logger.info(f"Processing Email: From={sender}, Subject={subject}, Date={received_at}")

            if "no-reply@accounts.google.com" in sender:
                logger.info(f"Skipping Google security email from {sender}")
                continue

            if any(promo in subject.lower() for promo in ["offer", "discount", "sale", "promotional", "newsletter"]):
                logger.info(f"Skipping promotional email: {subject}")
                continue

            is_sms_forwarder = "info@aradhanajewellers.com" in sender or "[SMSForwarder]" in subject
            if not is_sms_forwarder:
                logger.info(f"Email skipped: not an SMS-forwarder message ({sender} / {subject})")
                continue

            logger.info(f"Classified as SMS_FORWARDER: {subject}")
            parsed_sms = parse_bank_sms(body)
            if not parsed_sms.amount or parsed_sms.amount <= 0:
                logger.warning(f"SMSForwarder skip: No amount found or amount <= 0. Body: {body[:100]}...")
                continue

            direction = detect_credit_or_debit(body)
            if not direction:
                logger.warning("SMSForwarder skip: transaction direction could not be determined")
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

            # sms_parser.parse_bank_sms() can hand back several different
            # shapes depending on which branch matched: the ICICI branch
            # produces "YYYY-MM-DD HH:MM:SS" (has a real time), but the
            # general fallback only ever captures a bare date - "DD-MM-YYYY",
            # "DD/MM/YYYY", or "DD Mon YYYY" - with no time component at all.
            # Only trying fromisoformat()/the ICICI format meant every one of
            # those fallback-branch dates silently failed to parse and got
            # replaced with the email's arrival time instead of what the bank
            # actually stated - wrong whenever an alert sat in the inbox a
            # while before being polled. Try every shape the parser can
            # actually produce; for a date-only match, keep the email's
            # time-of-day (closer to the truth than midnight) but use the
            # bank's stated date.
            ts = received_at
            if parsed_sms.transaction_date:
                raw_date = parsed_sms.transaction_date.strip()
                parsed_ts = None
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        parsed_ts = datetime.strptime(raw_date, fmt)
                        break
                    except ValueError:
                        continue
                if parsed_ts is None:
                    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"):
                        try:
                            date_only = datetime.strptime(raw_date, fmt)
                            parsed_ts = date_only.replace(
                                hour=received_at.hour, minute=received_at.minute, second=received_at.second,
                            )
                            break
                        except ValueError:
                            continue
                if parsed_ts is not None:
                    ts = parsed_ts
                else:
                    logger.warning(f"Could not parse transaction_date {raw_date!r}; using email arrival time instead")

            new_sms = SMSAlert(
                sender=sms_sender,
                transaction_timestamp=ts,
                bank_name=parsed_sms.sender_bank or "ICICI",
                account_suffix=parsed_sms.account_suffix,
                credit_or_debit=direction,
                amount=parsed_sms.amount,
                utr_reference=parsed_sms.utr_reference,
                payer_name=parsed_sms.payer_name,
                raw_body=body,
                email_message_id=email_data["message_id"],
                parsed_confidence=1.0 if parsed_sms.confidence == "HIGH" else 0.5
            )
            db.add(new_sms)
            events_found += 1
            logger.info(f"Stored SMSAlert: {new_sms.utr_reference or new_sms.email_message_id}, direction={direction}")

        if newest_ts > checkpoint:
            save_checkpoint(db, newest_ts)

        db.commit()
        update_email_status(
            last_sync=now_ist().isoformat(),
            next_sync=(datetime.now().timestamp() + EMAIL_POLL_INTERVAL_SECONDS),
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
            time.sleep(EMAIL_POLL_INTERVAL_SECONDS)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info("Email poller thread started.")
