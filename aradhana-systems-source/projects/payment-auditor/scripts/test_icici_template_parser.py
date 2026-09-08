import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from backend.imap_collector import build_imap_config, connect_imap, fetch_labeled_emails, convert_imap_message_to_raw_email
from backend.email_ingestion.icici_template_parser import ICICITemplateParser

load_dotenv()

# Configuration
IMPORT_BASE = r"C:\Aradhana\BankImports"
JSON_OUT = os.path.join(IMPORT_BASE, "icici_parser_test_results.json")
AUDIT_LOG_DIR = r"C:\Aradhana\AuditLogs"

os.makedirs(IMPORT_BASE, exist_ok=True)
os.makedirs(AUDIT_LOG_DIR, exist_ok=True)

def run_test():
    print("Running ICICI Template Parser Test...")
    
    parser = ICICITemplateParser()
    config = build_imap_config()
    mail = connect_imap(config)
    
    raw_msgs = fetch_labeled_emails(mail, "BANK_ICICI", limit=20)
    
    results = []
    template_counts = {}
    
    parsed_successfully = 0
    needs_review = 0
    failed = 0
    
    for raw_msg in raw_msgs:
        email_obj = convert_imap_message_to_raw_email(raw_msg, "BANK_ICICI")
        if not email_obj: continue
        
        # Parse
        res = parser.parse(email_obj.subject, email_obj.raw_body)
        res["message_id"] = email_obj.message_id
        res["timestamp"] = datetime.now().isoformat()
        
        # Logging/Counters
        t_name = res["template"]
        template_counts[t_name] = template_counts.get(t_name, 0) + 1
        
        if res["is_transaction"]:
            if res["status"] == "GREEN":
                parsed_successfully += 1
            else:
                needs_review += 1
        elif res["status"] == "NON_FINANCIAL_ALERT" or res["status"] == "SECURITY_ALERT":
            # Successfully categorized non-financial emails
            pass
        else:
            failed += 1
            
        results.append(res)
        
        # Immutable Audit Log
        log_filename = f"PARSER_TEST_{t_name}_{email_obj.message_id.replace('<','').replace('>','').replace('@','_')}.json"
        log_path = os.path.join(AUDIT_LOG_DIR, log_filename)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=4)

    mail.logout()

    report = {
        "timestamp": datetime.now().isoformat(),
        "total_emails": len(results),
        "parsed_successfully": parsed_successfully,
        "needs_review": needs_review,
        "failed": failed,
        "template_breakdown": template_counts,
        "details": results
    }

    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4)
        
    print(f"Test complete. Report saved to {JSON_OUT}")
    print(f"Template Breakdown: {template_counts}")

if __name__ == "__main__":
    run_test()
