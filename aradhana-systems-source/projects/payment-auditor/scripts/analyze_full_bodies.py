import imaplib
import email
import os
import re
from dotenv import load_dotenv
from backend.imap_collector import build_imap_config, connect_imap, fetch_labeled_emails, convert_imap_message_to_raw_email

load_dotenv()

def strip_html(html):
    if not html: return ""
    clean = re.sub(r'<(script|style).*?>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r'<.*?>', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def analyze_full_bodies():
    config = build_imap_config()
    mail = connect_imap(config)
    
    print("ANALYZING FULL BODIES FROM BANK_ICICI...")
    print("="*60)
    
    raw_msgs = fetch_labeled_emails(mail, "BANK_ICICI", limit=5)
    
    for raw_msg in raw_msgs:
        email_obj = convert_imap_message_to_raw_email(raw_msg, "BANK_ICICI")
        if not email_obj: continue
        
        print(f"SUBJECT: {email_obj.subject}")
        cleaned = strip_html(email_obj.raw_body)
        print(f"CLEANED TEXT: {cleaned}")
        
        # Look for typical ICICI patterns in the full text
        # e.g. "is credited with", "UTR", "Transaction of"
        if "credited" in cleaned.lower():
            print("  [PATTERN DETECTED: Credit Alert]")
        if "UTR" in cleaned:
            print("  [PATTERN DETECTED: UTR Found]")
            
        print("-" * 40)
        
    mail.logout()

if __name__ == "__main__":
    analyze_full_bodies()
