import json
import os
from datetime import datetime

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports\JSON"
HEALTH_REPORT = os.path.join(EXPORT_BASE, "system_health_report.json")
INVOICE_EXTRACT = os.path.join(EXPORT_BASE, "daily_invoice_extract.json")
PARSED_TRANS = os.path.join(EXPORT_BASE, "parsed_transactions.json")
RECON_RESULTS = os.path.join(EXPORT_BASE, "reconciliation_results.json")
QUEUE = os.path.join(EXPORT_BASE, "review_queue.json")
SUMMARY_OUT = os.path.join(EXPORT_BASE, "validation_run_report.json")

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def generate_summary():
    print("Generating Validation Run Report...")
    
    health = load_json(HEALTH_REPORT)
    invoices = load_json(INVOICE_EXTRACT)
    emails = load_json(PARSED_TRANS)
    recon = load_json(RECON_RESULTS)
    queue = load_json(QUEUE)

    summary = {
        "timestamp": datetime.now().isoformat(),
        "metrics": {
            "invoices_extracted": invoices.get("extracted_count", 0) if invoices else 0,
            "invoices_failed": len([i for i in invoices.get("invoices", []) if i.get("invoice", {}).get("status") == "EXTRACTION_FAILED"]) if invoices else 0,
            "bank_emails_imported": emails.get("count", 0) if emails else 0,
            "matches_found": len([r for r in recon if r["status"] == "BANK_CONFIRMED"]) if recon else 0,
            "review_queue_count": queue.get("count", 0) if queue else 0,
            "system_status": health.get("overall_status", "UNKNOWN") if health else "UNKNOWN"
        }
    }

    with open(SUMMARY_OUT, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4)
        
    print(f"Executive Summary saved to {SUMMARY_OUT}")
    print(f"System Status: {summary['metrics']['system_status']}")

if __name__ == "__main__":
    generate_summary()
