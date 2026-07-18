import os
import json
from datetime import datetime

# Configuration
IMPORT_BASE = r"C:\Aradhana\BankImports"
PAYMENTS_IN = os.path.join(IMPORT_BASE, "bank_payments_until_yesterday.json")
ORGANIZED_OUT = os.path.join(IMPORT_BASE, "payment_received_organized.json")

def organize_payments():
    print("Organizing Received Payment Data...")
    
    if not os.path.exists(PAYMENTS_IN):
        # Create empty if missing
        with open(ORGANIZED_OUT, "w", encoding="utf-8") as f:
            json.dump({"timestamp": datetime.now().isoformat(), "total_count": 0, "payments": []}, f, indent=4)
        print("No payments found to organize.")
        return

    with open(PAYMENTS_IN, "r", encoding="utf-8") as f:
        payments = json.load(f)

    # Deduplicate and Group
    unique_payments = {}
    duplicates_count = 0
    
    for p in payments:
        # Create a unique key for deduplication
        utr = p.get("utr") or "NOUTR"
        amt = p.get("amount") or 0.0
        date = p.get("transaction_date") or "NODATE"
        
        key = f"{utr}_{amt}_{date}"
        
        if key in unique_payments:
            duplicates_count += 1
            unique_payments[key]["source_emails"].append(p.get("message_id"))
        else:
            p["source_emails"] = [p.get("message_id")]
            unique_payments[key] = p

    final_payments = list(unique_payments.values())

    with open(ORGANIZED_OUT, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_count": len(final_payments),
            "duplicates_removed": duplicates_count,
            "payments": final_payments
        }, f, indent=4)

    print(f"Organized {len(final_payments)} unique payments. Removed {duplicates_count} duplicates.")

if __name__ == "__main__":
    organize_payments()
