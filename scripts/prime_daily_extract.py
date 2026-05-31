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
    
    desktop = Desktop(backend="win32")
    prime_window = None
    for win in desktop.windows():
        if "SHREE ARADHANA JEWELLERS" in win.window_text():
            prime_window = win
            break
    
    if not prime_window:
        logger.error("Prime window not found.")
        return

    # Check for GST Register
    register_form = None
    for child in prime_window.descendants(class_name="ThunderRT6FormDC"):
        if "Register" in child.window_text():
            register_form = child
            break

    extracted_invoices = []

    if register_form:
        logger.info(f"GST Register detected: {register_form.window_text()}")
        tbs = register_form.descendants(class_name="ThunderRT6TextBox")
        raw_values = [tb.window_text().strip() for tb in tbs]
        
        # Grid heuristic: iterate through textboxes in strides
        # Based on log analysis, stride is approximately 40-50 per row
        stride = 50 
        for i in range(0, len(raw_values), stride):
            row = raw_values[i:i+stride]
            if len(row) > 25 and "/2026/" in str(row):
                # Attempt to map row to invoice structure
                inv = {
                    "invoice_no": row[25] if len(row) > 25 else "UNKNOWN",
                    "invoice_date": row[10] if len(row) > 10 else "UNKNOWN",
                    "customer_code": row[6] if len(row) > 6 else "UNKNOWN",
                    "invoice_total": 0.0,
                    "payment_rows": [],
                    "payment_status": "YELLOW", # Needs verification
                    "reason": "GRID_EXTRACT"
                }
                try:
                    inv["invoice_total"] = float(row[29].replace(",", ""))
                except (ValueError, IndexError):
                    pass
                extracted_invoices.append(inv)
    else:
        # 1. Extract Single Invoice Header
        invoice_data = extract_invoice_header()
        if invoice_data:
            # 2. Extract Payment Details
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

            extracted_invoices.append({
                "invoice": invoice_data,
                "payment_rows": payment_rows,
                "validation": {
                    "payment_status": payment_status,
                    "reason": reason,
                    "total_payments": total_payments,
                    "invoice_total": invoice_total
                }
            })

    # 4. Save
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "extracted_count": len(extracted_invoices),
        "invoices": extracted_invoices
    }

    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=4)
    
    logger.info(f"Daily extract complete. Extracted {len(extracted_invoices)} invoices.")
    return output_data

if __name__ == "__main__":
    result = run_daily_extract()
    if result:
        print(f"Success: Daily extract complete. Extracted {result['extracted_count']} invoices.")
    else:
        print("Daily extract failed.")
