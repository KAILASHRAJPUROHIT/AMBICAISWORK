import imaplib
import email
import os
from typing import List, Dict, Any, Optional
from backend.schemas import RawEmail
from datetime import datetime
from email.utils import parsedate_to_datetime
from email.header import decode_header, make_header

def build_imap_config() -> Dict[str, str]:
    """
    Builds IMAP configuration from environment variables.
    Validates that required credentials exist.
    """
    host = os.getenv("IMAP_HOST", "imap.gmail.com")
    user = os.getenv("IMAP_USER")
    password = os.getenv("IMAP_PASSWORD")

    if not user or not password:
        raise ValueError("IMAP credentials (IMAP_USER, IMAP_PASSWORD) missing in environment variables")

    return {
        "host": host,
        "user": user,
        "password": password,
    }

def connect_imap(config: Dict[str, str]) -> imaplib.IMAP4_SSL:
    """
    Connects to the IMAP server using the provided configuration.
    Returns a connection object.
    """
    try:
        mail = imaplib.IMAP4_SSL(config["host"])
        mail.login(config["user"], config["password"])
        return mail
    except Exception as e:
        raise ConnectionError(f"Failed to connect to IMAP server: {str(e)}")

def decode_mime_header(header_value: Optional[str]) -> str:
    """
    Decodes MIME-encoded headers safely.
    Preserves original value if decoding fails.
    """
    if not header_value:
        return ""
    try:
        return str(make_header(decode_header(header_value)))
    except Exception:
        return header_value

def fetch_labeled_emails(mail: imaplib.IMAP4_SSL, label_name: str, limit: int = 50) -> List[bytes]:
    """
    Fetches raw emails for a specific Gmail label in READ-ONLY mode.
    """
    # Select the mailbox (label) in readonly mode to prevent marking as read or other side effects
    status, _ = mail.select(label_name, readonly=True)
    if status != 'OK':
        return []

    # Search for all emails in the selected label
    status, data = mail.search(None, 'ALL')
    if status != 'OK':
        return []

    mail_ids = data[0].split()
    # Get the latest emails up to the limit
    latest_ids = mail_ids[-limit:]
    
    raw_emails = []
    for m_id in latest_ids:
        status, data = mail.fetch(m_id, '(RFC822)')
        if status == 'OK':
            raw_emails.append(data[0][1])
            
    return raw_emails

def convert_imap_message_to_raw_email(raw_msg: bytes, label: str) -> Optional[RawEmail]:
    """
    Converts raw IMAP message bytes to a RawEmail Pydantic model.
    Decodes MIME headers safely.
    """
    msg = email.message_from_bytes(raw_msg)
    
    message_id = msg.get('Message-ID', '')
    sender = decode_mime_header(msg.get('From', ''))
    subject = decode_mime_header(msg.get('Subject', ''))
    date_str = msg.get('Date', '')
    
    try:
        date = parsedate_to_datetime(date_str)
    except Exception:
        date = datetime.utcnow()

    raw_body = ""
    html_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get('Content-Disposition'))
            if 'attachment' in content_disposition:
                continue
            
            payload = part.get_payload(decode=True)
            if not payload:
                continue
                
            charset = part.get_content_charset() or 'utf-8'
            if content_type == 'text/plain':
                raw_body += payload.decode(charset, errors='ignore')
            elif content_type == 'text/html':
                html_body += payload.decode(charset, errors='ignore')
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            raw_body = payload.decode(msg.get_content_charset() or 'utf-8', errors='ignore')

    # Fallback to HTML if plain text is empty
    if not raw_body.strip() and html_body:
        raw_body = html_body

    if not message_id or not sender:
        return None

    return RawEmail(
        message_id=message_id,
        sender=sender,
        subject=subject,
        date=date,
        raw_body=raw_body,
        label=label
    )

def collect_bank_emails(mail: imaplib.IMAP4_SSL, labels: List[str]) -> List[RawEmail]:
    """
    Orchestrates email collection across multiple labels.
    Prevents duplicates within the same session using message_id.
    """
    collected_emails: List[RawEmail] = []
    seen_ids = set()

    for label in labels:
        raw_msgs = fetch_labeled_emails(mail, label)
        for raw_msg in raw_msgs:
            raw_email = convert_imap_message_to_raw_email(raw_msg, label)
            if raw_email and raw_email.message_id not in seen_ids:
                collected_emails.append(raw_email)
                seen_ids.add(raw_email.message_id)

    return collected_emails
