import json
import os
from datetime import datetime

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports\JSON"
INVOICE_EXTRACT = os.path.join(EXPORT_BASE, "daily_invoice_extract.json")
RECON_RESULTS = os.path.join(EXPORT_BASE, "reconciliation_results.json")
QUEUE_OUT = os.path.join(EXPORT_BASE, "review_queue.json")

def generate_queue():
    print("Generating Review Queue...")
    queue = []
    
    # 1. Extraction Failures
    if os.path.exists(INVOICE_EXTRACT):
        with open(INVOICE_EXTRACT, "r", encoding="utf-8") as f:
            data = json.load(f)
            for inv in data.get("invoices", []):
                if inv.get("invoice", {}).get("status") == "EXTRACTION_FAILED":
                    queue.append({
                        "type": "EXTRACTION_FAILURE",
                        "id": inv.get("invoice", {}).get("timestamp"),
                        "details": inv.get("invoice")
                    })

    # 2. Reconciliation Issues (RED/YELLOW/NEEDS_REVIEW)
    if os.path.exists(RECON_RESULTS):
        with open(RECON_RESULTS, "r", encoding="utf-8") as f:
            results = json.load(f)
            for res in results:
                if res["color"] in ["RED", "YELLOW"]:
                    queue.append({
                        "type": "RECONCILIATION_ISSUE",
                        "id": res["invoice_no"],
                        "details": res
                    })

    # 3. Save Queue
    with open(QUEUE_OUT, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "count": len(queue),
            "items": queue
        }, f, indent=4)
        
    print(f"Review Queue generated with {len(queue)} items at {QUEUE_OUT}")

if __name__ == "__main__":
    generate_queue()
