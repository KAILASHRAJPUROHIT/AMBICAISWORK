import os
import json
import logging
import re
from datetime import datetime
from dotenv import load_dotenv
from backend.imap_collector import build_imap_config, connect_imap, fetch_labeled_emails, convert_imap_message_to_raw_email

load_dotenv()

# Configuration
IMPORT_BASE = r"C:\Aradhana\BankImports"
JSON_OUT = os.path.join(IMPORT_BASE, "icici_format_discovery.json")
SUMMARY_OUT = os.path.join(IMPORT_BASE, "icici_format_summary.md")

os.makedirs(IMPORT_BASE, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def redact_sensitive_info(text: str) -> str:
    """
    Redacts account numbers, names, and balances while preserving transaction keywords.
    """
    if not text:
        return ""
    
    # 1. Redact Account Numbers (e.g. XX123, XXXXX4567, 123456789012)
    # Looking for 'A/c' followed by alphanumeric or just long digits
    text = re.sub(r"(?:A/c\s*|account\s*)[X\d]{3,15}", "[ACCOUNT_REDACTED]", text, flags=re.IGNORECASE)
    
    # 2. Redact Balances
    # e.g. "Available Balance is INR 5,000.00"
    text = re.sub(r"(?:balance\s+is\s+)(?:INR|Rs\.?)\s*[\d,]+\.\d{2}", "balance is [BALANCE_REDACTED]", text, flags=re.IGNORECASE)
    
    # 3. Heuristic Name Redaction (experimental)
    # Redact uppercase words in 'Info' string that aren't keywords
    keywords = {"UPI", "INF", "NEFT", "IMPS", "RTGS", "CHQ", "DR", "CR", "ICICI", "BANK", "CREDITED", "DEBITED", "INR"}
    
    def name_replacer(match):
        val = match.group(0)
        if val.upper() in keywords or "/" in val:
            return val
        return "[NAME_REDACTED]"
    
    # Look for likely names in Info strings (words between slashes or at end)
    text = re.sub(r"(?<=/)([A-Z\s]{3,30})(?=/|$)", "[NAME_REDACTED]", text)

    return text

def discover_icici_formats():
    logger.info("Starting ICICI Email Format Discovery")
    
    discovery_results = []
    
    try:
        config = build_imap_config()
        mail = connect_imap(config)
        
        logger.info("Fetching latest 20 emails from BANK_ICICI")
        raw_msgs = fetch_labeled_emails(mail, "BANK_ICICI", limit=20)
        
        for raw_msg in raw_msgs:
            email_obj = convert_imap_message_to_raw_email(raw_msg, "BANK_ICICI")
            if not email_obj:
                continue
                
            # Basic info
            entry = {
                "subject": redact_sensitive_info(email_obj.subject),
                "sender": email_obj.sender,
                "date": email_obj.date.isoformat(),
                "body_sample": redact_sensitive_info(email_obj.raw_body[:1000]),
                "content_type": "text/plain", # Defaulting as per collector logic
                "message_id": email_obj.message_id
            }
            discovery_results.append(entry)
            
        mail.logout()

        # Grouping by Template (Heuristic)
        templates = {}
        for res in discovery_results:
            # Create a signature from the subject (removing redacted parts for grouping)
            sig = res["subject"].replace("[ACCOUNT_REDACTED]", "ACC").strip()
            if sig not in templates:
                templates[sig] = {"count": 0, "sample": res["body_sample"], "subjects": set()}
            templates[sig]["count"] += 1
            templates[sig]["subjects"].add(res["subject"])

        # Save JSON
        with open(JSON_OUT, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "emails_probed": len(discovery_results),
                "data": discovery_results
            }, f, indent=4)

        # Save Summary Markdown
        with open(SUMMARY_OUT, "w", encoding="utf-8") as f:
            f.write("# ICICI Email Format Discovery Summary\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n")
            f.write(f"**Emails Probed:** {len(discovery_results)}\n\n")
            
            f.write("## Template Analysis\n\n")
            for i, (sig, data) in enumerate(templates.items()):
                f.write(f"### Template {chr(65+i)} ({data['count']} occurrences)\n")
                f.write(f"**Signature:** `{sig}`\n\n")
                f.write("**Body Sample:**\n```text\n")
                f.write(data["sample"])
                f.write("\n```\n\n")
                f.write("---\n\n")

        print(f"Discovery complete. JSON: {JSON_OUT}, Summary: {SUMMARY_OUT}")

    except Exception as e:
        logger.exception(f"Discovery failed: {e}")

if __name__ == "__main__":
    discover_icici_formats()
