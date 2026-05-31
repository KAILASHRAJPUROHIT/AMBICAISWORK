import os
import json
import logging
from datetime import datetime
from pywinauto import Desktop

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
JSON_OUT = os.path.join(EXPORT_BASE, "JSON", "raw_invoice.json")
LOG_OUT = os.path.join(EXPORT_BASE, "Logs", "invoice_extractor.log")

# Mapping from docs/prime_invoice_field_mapping.md
MAP = {
    "invoice_no": 25,
    "invoice_date": 10,
    "customer_code": 6,
    "customer_name": 4,
    "mobile": 20,
    "invoice_total": 29,
    "taxable_amount": 54, # Item level, but used as heuristic for MVP
    "cgst": 56,
    "sgst": 58
}

os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
os.makedirs(os.path.dirname(LOG_OUT), exist_ok=True)

logging.basicConfig(filename=LOG_OUT, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def extract_invoice_header():
    logger.info("Starting Invoice Header Extraction")
    try:
        desktop = Desktop(backend="win32")
        prime_window = None
        for win in desktop.windows():
            if "SHREE ARADHANA JEWELLERS" in win.window_text():
                prime_window = win
                break
        
        if not prime_window:
            logger.error("Prime window not found.")
            return None

        # Main Bill Form (Purchase or Sales)
        bill_form = None
        for child in prime_window.descendants(class_name="ThunderRT6FormDC"):
            if "Bill" in child.window_text() and "Payment Detail" not in child.window_text():
                bill_form = child
                break
        
        if not bill_form:
            # Fallback to MDI if no specific bill form detected
            bill_form = prime_window

        tbs = bill_form.descendants(class_name="ThunderRT6TextBox")
        
        invoice_data = {
            "timestamp": datetime.now().isoformat(),
            "invoice_no": None,
            "invoice_date": None,
            "customer_code": None,
            "customer_name": None,
            "mobile": None,
            "invoice_total": 0.0,
            "taxable_amount": 0.0,
            "cgst": 0.0,
            "sgst": 0.0
        }

        for key, idx in MAP.items():
            if idx < len(tbs):
                val = tbs[idx].window_text().strip()
                if "amount" in key or "gst" in key or "total" in key:
                    try:
                        invoice_data[key] = float(val.replace(",", ""))
                    except ValueError:
                        pass
                else:
                    invoice_data[key] = val

        # Clean up mobile
        if invoice_data["mobile"] and ".Mob." in invoice_data["mobile"]:
            invoice_data["mobile"] = invoice_data["mobile"].split(".Mob.")[-1].strip()

        with open(JSON_OUT, "w", encoding="utf-8") as f:
            json.dump(invoice_data, f, indent=4)
        
        logger.info(f"Extracted invoice {invoice_data.get('invoice_no')}")
        return invoice_data

    except Exception as e:
        logger.exception("Error in Invoice Extractor")
        return None

if __name__ == "__main__":
    data = extract_invoice_header()
    if data:
        print(f"Success: Extracted invoice {data.get('invoice_no')} to {JSON_OUT}")
    else:
        print("Failed to extract invoice.")
