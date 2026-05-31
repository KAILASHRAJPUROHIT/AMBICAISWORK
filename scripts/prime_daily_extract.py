import os
import json
import logging
from datetime import datetime
from pywinauto import Desktop
from prime_invoice_extractor import extract_invoice_header
from prime_payment_detail_extractor import extract_payment_details

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
JSON_OUT = os.path.join(EXPORT_BASE, "JSON", "daily_extract.json")
LOG_OUT = os.path.join(EXPORT_BASE, "Logs", "daily_extract.log")

os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
os.makedirs(os.path.dirname(LOG_OUT), exist_ok=True)

logging.basicConfig(filename=LOG_OUT, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def run_daily_extract():
    logger.info("Starting Daily Extract Orchestration")
    
    # 1. Extract Main Invoice Header
    invoice_data = extract_invoice_header()
    if not invoice_data:
        logger.error("Failed to extract invoice header.")
        return

    # 2. Extract Payment Details (assuming user has it open or we found it)
    payment_rows = extract_payment_details()
    if payment_rows is None:
        payment_rows = []

    # 3. Consolidation & Validation
    total_payments = sum(p["amount"] for p in payment_rows)
    invoice_total = invoice_data.get("invoice_total", 0.0)
    
    payment_status = "GREEN"
    reason = None
    
    if abs(invoice_total - total_payments) > 0.01:
        payment_status = "RED"
        reason = "PAYMENT_TOTAL_MISMATCH"
        logger.warning(f"Validation Mismatch: Invoice={invoice_total}, Payments={total_payments}")

    daily_data = {
        "timestamp": datetime.now().isoformat(),
        "invoice": invoice_data,
        "payment_rows": payment_rows,
        "validation": {
            "payment_status": payment_status,
            "reason": reason,
            "total_payments": total_payments,
            "invoice_total": invoice_total
        }
    }

    # 4. Save
    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(daily_data, f, indent=4)
    
    logger.info("Daily extract complete.")
    return daily_data

if __name__ == "__main__":
    result = run_daily_extract()
    if result:
        print(f"Success: Daily extract complete for {result['invoice'].get('invoice_no')}")
        print(f"Validation Status: {result['validation']['payment_status']}")
    else:
        print("Daily extract failed.")
