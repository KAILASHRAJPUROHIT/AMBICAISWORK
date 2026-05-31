import os
import json
import subprocess
import time
from datetime import datetime

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
FINAL_OUT = os.path.join(EXPORT_BASE, "JSON", "single_invoice_validated.json")
SCRIPTS_DIR = "scripts"
PYTHON_32 = r"C:\Aradhana\venv32\Scripts\python.exe"

def run_script(script_name):
    print(f"Executing {script_name} using 32-bit Python...")
    try:
        # Explicitly use the 32-bit python interpreter
        result = subprocess.run([PYTHON_32, os.path.join(SCRIPTS_DIR, script_name)], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error running {script_name}: {result.stderr}")
        return result.stdout
    except Exception as e:
        print(f"Failed to execute {script_name}: {e}")
        return None

def orchestrate_validation():
    print("Starting Prime Extraction Validation Flow...")
    
    # 1. Force Visibility
    run_script("prime_force_visibility.py")
    time.sleep(1)
    
    # 2. Active Form Dump
    run_script("prime_active_form_dump.py")
    
    # 3. Extract Invoice
    run_script("prime_invoice_extractor.py")
    
    # 4. Extract Payment Details
    run_script("prime_payment_detail_extractor.py")
    
    # Load Results
    invoice_path = os.path.join(EXPORT_BASE, "JSON", "raw_invoice.json")
    payment_path = os.path.join(EXPORT_BASE, "JSON", "raw_payment_rows.json")
    
    if not os.path.exists(invoice_path):
        print("Missing invoice extraction result.")
        return

    with open(invoice_path, "r", encoding="utf-8") as f:
        inv_data = json.load(f)
    
    pay_rows = []
    if os.path.exists(payment_path):
        with open(payment_path, "r", encoding="utf-8") as f:
            pay_data = json.load(f)
            pay_rows = pay_data.get("payment_rows", [])

    # Consolidate
    payment_total = sum(p.get("amount", 0.0) for p in pay_rows)
    invoice_total = inv_data.get("fields", {}).get("invoice_total", 0.0)
    
    validation_status = "NEEDS_REVIEW"
    if inv_data.get("status") == "GREEN":
        if abs(invoice_total - payment_total) < 0.01 and payment_total > 0:
            validation_status = "PASS"
        elif payment_total == 0 and invoice_total > 0:
             validation_status = "NEEDS_REVIEW_MISSING_PAYMENTS"
        else:
             validation_status = "FAIL_TOTAL_MISMATCH"

    final_result = {
        "timestamp": datetime.now().isoformat(),
        "invoice_no": inv_data.get("fields", {}).get("invoice_no"),
        "date": inv_data.get("fields", {}).get("invoice_date"),
        "customer_name": inv_data.get("fields", {}).get("customer_name"),
        "invoice_total": invoice_total,
        "payment_rows": pay_rows,
        "payment_total": payment_total,
        "validation_status": validation_status,
        "extraction_status": inv_data.get("status"),
        "raw_invoice": inv_data
    }

    with open(FINAL_OUT, "w", encoding="utf-8") as f:
        json.dump(final_result, f, indent=4)
    
    print(f"Consolidated result saved to {FINAL_OUT}")
    print(f"Validation Result: {validation_status}")

if __name__ == "__main__":
    orchestrate_validation()
