import os
import json
import logging
import sys
import struct
import psutil
from datetime import datetime, timedelta
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

def validate_runtime():
    """Ensures extraction is running on 32-bit Python."""
    is_32bit = struct.calcsize("P") * 8 == 32
    if not is_32bit:
        msg = "FATAL ERROR: Prime extraction MUST run on 32-bit Python."
        logger.critical(msg)
        print(msg)
        sys.exit(1)

def run_daily_extract():
    logger.info("Starting Bulk Daily Extract (Yesterday's Invoices)")
    validate_runtime()
    
    desktop = Desktop(backend="win32")
    
    # Get all windows for FA.exe
    process_pids = [p.info['pid'] for p in psutil.process_iter(['pid', 'name']) if p.info['name'] and p.info['name'].lower() == "fa.exe"]
    if not process_pids:
        logger.error("FA.exe process not found.")
        return
    
    # 1. Identify active Sales Bill form or GST Register
    register_form = None
    for win in desktop.windows():
        if win.process_id() in process_pids:
            title = win.window_text()
            if "Register" in title:
                register_form = win
                break
            # Also check descendants if the title isn't on the top window
            for child in win.descendants(class_name="ThunderRT6FormDC"):
                if "Register" in child.window_text():
                    register_form = child
                    break
            if register_form: break
    
    if not register_form:
        logger.error("GST Register form not found.")
        return

    logger.info(f"Targeting Form: {register_form.window_text()} [Handle: {register_form.handle}]")

    extracted_invoices = []
    failed_invoices = []
    
    # Yesterday filter
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")
    logger.info(f"Filtering for date: {yesterday_str}")

    if register_form:
        logger.info(f"GST Register detected. Probing grid...")
        tbs = register_form.descendants(class_name="ThunderRT6TextBox")
        raw_values = [tb.window_text().strip() for tb in tbs]
        
        # Grid stride heuristic
        stride = 50 
        for i in range(0, len(raw_values), stride):
            row = raw_values[i:i+stride]
            if len(row) > 25:
                row_date = row[10]
                if row_date == yesterday_str:
                    inv = {
                        "invoice_no": row[25],
                        "invoice_date": row_date,
                        "customer_name": row[4], # A/c Name
                        "invoice_total": 0.0,
                        "payment_status": "NEEDS_REVIEW",
                        "extraction_source": "GRID"
                    }
                    try:
                        inv["invoice_total"] = float(row[29].replace(",", ""))
                        extracted_invoices.append(inv)
                    except Exception as e:
                        logger.error(f"Row extraction failure: {e}")
                        failed_invoices.append({"row": row, "error": str(e)})

    # Metrics
    metrics = {
        "timestamp": datetime.now().isoformat(),
        "date_filtered": yesterday_str,
        "visible_rows": len(extracted_invoices) + len(failed_invoices),
        "extracted": len(extracted_invoices),
        "failed": len(failed_invoices)
    }

    # Save
    output_data = {
        "metrics": metrics,
        "invoices": extracted_invoices
    }

    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=4)
        
    with open(os.path.join(EXPORT_BASE, "JSON", "daily_invoice_extract_failed.json"), "w", encoding="utf-8") as f:
        json.dump(failed_invoices, f, indent=4)
    
    logger.info(f"Bulk extract complete. {metrics['extracted']} successful.")
    return output_data

if __name__ == "__main__":
    result = run_daily_extract()
    if result:
        print(f"Success: Daily extract complete. Extracted {result['metrics']['extracted']} invoices.")
    else:
        print("Daily extract failed.")
