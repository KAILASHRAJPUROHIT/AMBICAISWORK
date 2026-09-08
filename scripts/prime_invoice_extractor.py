import os
import json
import logging
import re
import sys
import struct
from datetime import datetime
from pywinauto import Desktop
import psutil

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
JSON_OUT = os.path.join(EXPORT_BASE, "JSON", "raw_invoice.json")
LOG_OUT = os.path.join(EXPORT_BASE, "Logs", "invoice_extractor.log")

os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
os.makedirs(os.path.dirname(LOG_OUT), exist_ok=True)

logging.basicConfig(filename=LOG_OUT, level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Patterns - more lenient
RE_INVOICE_NO = re.compile(r".*(SG|SS|S1|S2|S4|S5)/\d{4}/\d+.*", re.IGNORECASE)
RE_DATE = re.compile(r".*\d{2}/\d{2}/\d{4}.*")
RE_MOBILE = re.compile(r"\d{10}")

def validate_runtime():
    """Ensures extraction is running on 32-bit Python."""
    is_32bit = struct.calcsize("P") * 8 == 32
    if not is_32bit:
        msg = "FATAL ERROR: Prime extraction MUST run on 32-bit Python to access MDI child controls."
        logger.critical(msg)
        print(msg)
        sys.exit(1)
    logger.info("Runtime validation successful (32-bit).")

def extract_invoice_header():
    logger.info("Starting Deterministic Pattern-Based Invoice Header Extraction (32-bit Optimized)")
    validate_runtime()
    try:
        desktop = Desktop(backend="win32")
        pids = []
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] and proc.info['name'].lower() == "fa.exe":
                pids.append(proc.info['pid'])
        
        if not pids:
            logger.error("FA.exe not found.")
            return {"status": "EXTRACTION_FAILED", "reason": "PRIME_NOT_RUNNING"}

        # 1. Identify active Sales Bill form
        bill_form = None
        for win in desktop.windows():
            if win.process_id() in pids and win.class_name() == "ThunderRT6MDIForm":
                # In 32-bit, child forms should be visible under MDIClient
                for client in win.children():
                    if client.class_name() == "MDIClient":
                        for child in client.children():
                            txt = child.window_text().strip()
                            if "Sales Bill" in txt and "Payment Detail" not in txt:
                                bill_form = child
                                logger.info(f"Targeting active bill form: '{txt}' [Handle: {child.handle}]")
                                break
                    if bill_form: break
            if bill_form: break

        if not bill_form:
            # Fallback to exhaustive search if MDI hierarchy traversal fails
            logger.warning("Standard MDI traversal failed. Searching all process descendants...")
            for win in desktop.windows():
                if win.process_id() in pids:
                    for child in win.descendants(class_name="ThunderRT6FormDC"):
                        txt = child.window_text().strip()
                        if "Sales Bill" in txt and "Payment Detail" not in txt:
                            bill_form = child
                            break
                if bill_form: break

        if not bill_form:
             logger.error("No valid Sales Bill form detected.")
             return {"status": "EXTRACTION_FAILED", "reason": "NO_VALID_FORM_FOUND"}

        # 2. Collect ALL non-empty textboxes in the target form
        raw_controls = []
        tbs = bill_form.descendants(class_name="ThunderRT6TextBox")
        for i, tb in enumerate(tbs):
            val = tb.window_text().strip()
            if val:
                raw_controls.append({
                    "value": val,
                    "rect": str(tb.rectangle()),
                    "index": i
                })

        logger.info(f"Collected {len(raw_controls)} non-empty textboxes from '{bill_form.window_text()}'.")

        # 3. Pattern-Based Extraction
        invoice_data = {
            "timestamp": datetime.now().isoformat(),
            "form_title": bill_form.window_text(),
            "fields": {
                "invoice_no": None,
                "invoice_date": None,
                "customer_name": None,
                "mobile": None,
                "invoice_total": 0.0
            },
            "confidence": "HIGH",
            "unresolved_fields": [],
            "raw_controls": raw_controls
        }

        amounts = []
        for ctrl in raw_controls:
            val = ctrl["value"]
            
            if not invoice_data["fields"]["invoice_no"] and RE_INVOICE_NO.match(val):
                invoice_data["fields"]["invoice_no"] = val
                continue
            
            if not invoice_data["fields"]["invoice_date"] and RE_DATE.match(val):
                invoice_data["fields"]["invoice_date"] = val
                continue

            if ".Mob." in val:
                parts = val.split(".Mob.")
                if len(parts) > 1:
                    invoice_data["fields"]["mobile"] = RE_MOBILE.search(parts[1]).group() if RE_MOBILE.search(parts[1]) else parts[1].strip()
                    invoice_data["fields"]["customer_name"] = parts[0].strip()

            try:
                clean_val = val.replace(",", "")
                if "." in clean_val:
                    amt = float(clean_val)
                    if amt > 0:
                        amounts.append(amt)
            except ValueError:
                pass

        if amounts:
            invoice_data["fields"]["invoice_total"] = max(amounts)
            invoice_data["fields"]["amount_candidates"] = sorted(list(set(amounts)), reverse=True)

        # 4. Validation
        missing = []
        for key in ["invoice_no", "invoice_date", "customer_name", "invoice_total"]:
            if not invoice_data["fields"][key]:
                missing.append(key)
        
        if missing:
            invoice_data["confidence"] = "LOW"
            invoice_data["unresolved_fields"] = missing
            invoice_data["status"] = "NEEDS_REVIEW"
        else:
            invoice_data["status"] = "GREEN"

        with open(JSON_OUT, "w", encoding="utf-8") as f:
            json.dump(invoice_data, f, indent=4)
        
        return invoice_data

    except Exception as e:
        logger.exception("Error in Invoice Header Extractor")
        return None

if __name__ == "__main__":
    data = extract_invoice_header()
    if data:
        if data.get("status") == "GREEN":
            print(f"Success: Extracted invoice {data['fields'].get('invoice_no')} with status GREEN")
        else:
            print(f"Extraction partial: {data.get('status')} - {data.get('reason') or data.get('unresolved_fields')}")
    else:
        print("Failed to extract invoice.")
