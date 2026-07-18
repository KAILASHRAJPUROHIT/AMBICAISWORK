from pathlib import Path
import sys
import json
import os
from datetime import datetime, date

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.reconciliation.status_engine_v2 import StatusEngineV2
from backend.reconciliation.payment_sla import PaymentSLAEngine

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports\JSON"
INVOICE_EXTRACT = os.path.join(EXPORT_BASE, "daily_invoice_extract.json")
PARSED_TRANS = os.path.join(EXPORT_BASE, "parsed_transactions.json")
RESULTS_OUT = os.path.join(EXPORT_BASE, "reconciliation_results.json")
SLA_OUT = os.path.join(EXPORT_BASE, "payment_sla_results.json")

def run_reconciliation():
    print("Starting Reconciliation Run (Validation MVP)...")
    
    # 1. Load Data
    if not os.path.exists(INVOICE_EXTRACT):
        print("Invoice extract not found.")
        return

    with open(INVOICE_EXTRACT, "r", encoding="utf-8") as f:
        inv_data = json.load(f)
    
    bank_transactions = []
    if os.path.exists(PARSED_TRANS):
        with open(PARSED_TRANS, "r", encoding="utf-8") as f:
            bank_data = json.load(f)
            bank_transactions = bank_data.get("transactions", [])

    status_engine = StatusEngineV2()
    sla_engine = PaymentSLAEngine()
    
    reconciliation_results = []
    sla_results = []
    
    today = date.today()

    for entry in inv_data.get("invoices", []):
        invoice = entry.get("invoice", {})
        if not invoice or invoice.get("status") == "EXTRACTION_FAILED":
            continue
            
        inv_no = invoice.get("fields", {}).get("invoice_no")
        inv_date = invoice.get("fields", {}).get("invoice_date")
        
        # Normalize date format for status engine (Expects YYYY-MM-DD or similar ISO)
        # Inv date is dd/mm/yyyy
        try:
            d_parts = inv_date.split("/")
            iso_date = f"{d_parts[2]}-{d_parts[1]}-{d_parts[0]}"
        except Exception:
            iso_date = datetime.now().strftime("%Y-%m-%d")

        for row in entry.get("payment_rows", []):
            # Attempt Matching
            match = None
            for tx in bank_transactions:
                if abs(tx["amount"] - row["amount"]) < 0.01:
                    match = tx
                    break
            
            # Determine Status & SLA
            status_res = status_engine.determine_status(iso_date, row, bank_evidence=match, current_date=today)
            
            recon_entry = {
                "invoice_no": inv_no,
                "payment_row": row,
                "status": status_res["payment_status"],
                "color": status_res["status_color"],
                "reason": status_res["reason"],
                "match": match
            }
            reconciliation_results.append(recon_entry)
            
            if "aging" in status_res:
                sla_results.append({
                    "invoice_no": inv_no,
                    "mode": row["payment_mode"],
                    "amount": row["amount"],
                    "sla": status_res["aging"]
                })

    # Save Results
    with open(RESULTS_OUT, "w", encoding="utf-8") as f:
        json.dump(reconciliation_results, f, indent=4)
        
    with open(SLA_OUT, "w", encoding="utf-8") as f:
        json.dump(sla_results, f, indent=4)

    print(f"Reconciliation results saved to {RESULTS_OUT}")
    print(f"SLA results saved to {SLA_OUT}")

if __name__ == "__main__":
    run_reconciliation()
