from pathlib import Path
import sys
import os
import json
from datetime import datetime

# Add the project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.reconciliation.status_engine_v2 import StatusEngineV2
# Configuration
IMPORT_BASE = r"C:\Aradhana\BankImports"
EXPORT_BASE = r"C:\Aradhana\PrimeExports\JSON"
RECON_BASE = r"C:\Aradhana\Reconciliation"
os.makedirs(RECON_BASE, exist_ok=True)

INVOICES_IN = os.path.join(EXPORT_BASE, "prime_invoices_yesterday.json")
PAYMENTS_IN = os.path.join(IMPORT_BASE, "payment_received_organized.json")
RECON_OUT = os.path.join(RECON_BASE, "reconciliation_until_yesterday.json")

def run_reconciliation():
    print("Running Deterministic Reconciliation...")
    
    if not os.path.exists(INVOICES_IN) or not os.path.exists(PAYMENTS_IN):
        print("Required input files missing.")
        return

    with open(INVOICES_IN, "r", encoding="utf-8") as f:
        inv_data = json.load(f)
    
    with open(PAYMENTS_IN, "r", encoding="utf-8") as f:
        bank_data = json.load(f)
        bank_payments = bank_data.get("payments", [])

    status_engine = StatusEngineV2()
    reconciliation_results = []
    
    for entry in inv_data.get("invoices", []):
        invoice = entry.get("invoice", {})
        if not invoice: continue
        
        inv_date_raw = invoice.get("fields", {}).get("invoice_date")
        # Normalize dd/mm/yyyy to yyyy-mm-dd
        try:
            d = inv_date_raw.split("/")
            inv_date = f"{d[2]}-{d[1]}-{d[0]}"
        except:
            inv_date = datetime.now().strftime("%Y-%m-%d")

        for row in entry.get("payment_rows", []):
            mode = row.get("payment_mode")
            # Only bank-originated
            if mode not in ["UPI", "IMPS", "NEFT", "RTGS_OR_CHEQUE", "CARD", "BANK", "RTGS", "CHEQUE", "ADVANCE", "BALANCE"]:
                continue

            # Find Match
            match = None
            for bp in bank_payments:
                if abs(bp["amount"] - row["amount"]) < 0.01:
                    # Potential Match
                    match = bp
                    break
            
            status_res = status_engine.determine_status(inv_date, row, bank_evidence=match)
            
            reconciliation_results.append({
                "invoice_no": invoice.get("fields", {}).get("invoice_no"),
                "payment_row": row,
                "status": status_res["payment_status"],
                "color": status_res["status_color"],
                "reason": status_res["reason"],
                "bank_match": match
            })

    with open(RECON_OUT, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": reconciliation_results
        }, f, indent=4)
        
    print(f"Reconciliation complete. {len(reconciliation_results)} rows processed.")

if __name__ == "__main__":
    run_reconciliation()
