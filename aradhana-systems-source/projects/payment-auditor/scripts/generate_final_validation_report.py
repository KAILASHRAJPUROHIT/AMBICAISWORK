import json
import os
from datetime import datetime

# Configuration
IMPORT_BASE = r"C:\Aradhana\BankImports"
EXPORT_BASE = r"C:\Aradhana\PrimeExports\JSON"
RECON_BASE = r"C:\Aradhana\Reconciliation"
QUEUE_BASE = r"C:\Aradhana\ReviewQueue"
REPORT_BASE = r"C:\Aradhana\Reports"
os.makedirs(REPORT_BASE, exist_ok=True)

EMAILS_RAW = os.path.join(IMPORT_BASE, "bank_emails_until_yesterday_raw.json")
PAYMENTS_PARSED = os.path.join(IMPORT_BASE, "bank_payments_until_yesterday.json")
NON_FINANCIAL = os.path.join(IMPORT_BASE, "bank_email_non_financial.json")
PARSE_FAILURES = os.path.join(IMPORT_BASE, "bank_email_parse_failures.json")
PRIME_INVOICES = os.path.join(EXPORT_BASE, "prime_invoices_yesterday.json")
RECON_RESULTS = os.path.join(RECON_BASE, "reconciliation_until_yesterday.json")
REVIEW_QUEUE = os.path.join(QUEUE_BASE, "review_queue_until_yesterday.json")

JSON_OUT = os.path.join(REPORT_BASE, "end_to_end_test_until_yesterday.json")
MD_OUT = os.path.join(REPORT_BASE, "end_to_end_test_until_yesterday.md")

def load_json_safe(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except: return None
    return None

def generate_final_report():
    print("Generating Final Validation Report...")
    
    emails_raw = load_json_safe(EMAILS_RAW)
    payments = load_json_safe(PAYMENTS_PARSED)
    non_fin = load_json_safe(NON_FINANCIAL)
    failures = load_json_safe(PARSE_FAILURES)
    invoices = load_json_safe(PRIME_INVOICES)
    recon = load_json_safe(RECON_RESULTS)
    queue = load_json_safe(REVIEW_QUEUE)

    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "bank_emails_collected": emails_raw.get("total_count", 0) if emails_raw else 0,
            "bank_payments_parsed": len(payments) if payments else 0,
            "non_financial_emails": len(non_fin) if non_fin else 0,
            "parse_failures": len(failures) if failures else 0,
            "prime_invoices_found": invoices.get("extracted_count", 0) if invoices else 0,
            "green_matches": len([r for r in recon.get("results", []) if r["status"] == "BANK_CONFIRMED"]) if recon else 0,
            "review_queue_count": queue.get("count", 0) if queue else 0
        }
    }

    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4)
        
    with open(MD_OUT, "w", encoding="utf-8") as f:
        f.write("# End-to-End Reconciliation Test Report\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write("## Metrics\n")
        for k, v in report["summary"].items():
            f.write(f"- **{k.replace('_',' ').title()}:** {v}\n")
            
    print(f"Final Report saved to {MD_OUT}")

if __name__ == "__main__":
    generate_final_report()
