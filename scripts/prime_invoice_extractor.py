import os
import json
import logging
import re
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

def extract_invoice_header():
    logger.info("Starting Exhaustive Pattern-Based Invoice Header Extraction")
    try:
        desktop = Desktop(backend="win32")
        pids = []
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] and proc.info['name'].lower() == "fa.exe":
                pids.append(proc.info['pid'])
        
        if not pids:
            logger.error("FA.exe not found.")
            return {"status": "EXTRACTION_FAILED", "reason": "PRIME_NOT_RUNNING"}

        # 1. Collect all non-empty textboxes in the entire process
        raw_controls = []
        all_windows = desktop.windows()
        for win in all_windows:
            try:
                if win.process_id() not in pids:
                    continue
                
                # Probing all descendants for textboxes
                tbs = win.descendants(class_name="ThunderRT6TextBox")
                for i, tb in enumerate(tbs):
                    val = tb.window_text().strip()
                    if val:
                        raw_controls.append({
                            "value": val,
                            "rect": str(tb.rectangle()),
                            "parent": win.window_text()
                        })
            except Exception:
                continue

        logger.info(f"Collected {len(raw_controls)} non-empty textboxes process-wide.")

        # 2. Pattern-Based Extraction from the pool
        invoice_data = {
            "timestamp": datetime.now().isoformat(),
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
            
            # Invoice No
            if not invoice_data["fields"]["invoice_no"] and RE_INVOICE_NO.match(val):
                invoice_data["fields"]["invoice_no"] = val
                logger.info(f"Found Invoice No: {val}")
                continue
            
            # Date
            if not invoice_data["fields"]["invoice_date"] and RE_DATE.match(val):
                invoice_data["fields"]["invoice_date"] = val
                logger.info(f"Found Date: {val}")
                continue

            # Customer & Mobile (Mob. marker)
            if ".Mob." in val:
                parts = val.split(".Mob.")
                if len(parts) > 1:
                    invoice_data["fields"]["mobile"] = RE_MOBILE.search(parts[1]).group() if RE_MOBILE.search(parts[1]) else parts[1].strip()
                    invoice_data["fields"]["customer_name"] = parts[0].strip()
                    logger.info(f"Found Customer/Mobile: {val}")

            # Amounts
            try:
                clean_val = val.replace(",", "")
                if "." in clean_val:
                    amt = float(clean_val)
                    if amt > 0:
                        amounts.append(amt)
            except ValueError:
                pass

        if amounts:
            # Heuristic: the largest amount is usually the total
            invoice_data["fields"]["invoice_total"] = max(amounts)
            invoice_data["fields"]["amount_candidates"] = sorted(list(set(amounts)), reverse=True)

        # 3. Validation
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
        logger.exception("Error in Exhaustive Extractor")
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
