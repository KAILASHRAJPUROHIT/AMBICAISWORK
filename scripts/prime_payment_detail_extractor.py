import os
import json
import logging
import sys
import struct
from datetime import datetime
from pywinauto import Desktop
import psutil

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
JSON_OUT = os.path.join(EXPORT_BASE, "JSON", "raw_payment_rows.json")
LOG_OUT = os.path.join(EXPORT_BASE, "Logs", "payment_extractor.log")

os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
os.makedirs(os.path.dirname(LOG_OUT), exist_ok=True)

logging.basicConfig(filename=LOG_OUT, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def validate_runtime():
    """Ensures extraction is running on 32-bit Python."""
    is_32bit = struct.calcsize("P") * 8 == 32
    if not is_32bit:
        msg = "FATAL ERROR: Prime extraction MUST run on 32-bit Python to access MDI child controls."
        logger.critical(msg)
        print(msg)
        sys.exit(1)

def extract_payment_details():
    logger.info("Starting Anchor-Based Payment Detail Extraction (32-bit Optimized)")
    validate_runtime()
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

        # Find the Payment Detail sub-form (likely MDI child or direct descendant in 32-bit)
        payment_form = None
        for child in prime_window.descendants(class_name="ThunderRT6FormDC"):
            if "Payment Detail" in child.window_text():
                payment_form = child
                break
        
        if not payment_form:
            logger.warning("Payment Detail form not visible.")
            return []

        logger.info(f"Found Payment Detail Form: {payment_form.window_text()}")
        
        # 1. Extract all textboxes and group by row (Y-coordinate proximity)
        tbs = payment_form.descendants(class_name="ThunderRT6TextBox")
        
        # Capture row-wise grouped data
        rows = {}
        for tb in tbs:
            rect = tb.rectangle()
            # Use top coordinate as primary key, rounding to handle slight variations
            y_key = round(rect.top / 5) * 5
            if y_key not in rows:
                rows[y_key] = []
            rows[y_key].append(tb)

        payment_rows = []
        for y in sorted(rows.keys()):
            # Sort controls in row from left to right
            row_ctrls = sorted(rows[y], key=lambda c: c.rectangle().left)
            row_data = [c.window_text().strip() for c in row_ctrls]
            
            if any(row_data):
                amount = 0.0
                mode = "UNKNOWN"
                reference = ""
                narration = ""
                
                # Heuristic: Amount is usually the first non-zero numeric at the end of the row
                # Or sometimes at a specific index. In VB6 grids, last fields are often totals.
                for val in reversed(row_data):
                    try:
                        clean_val = val.replace(",", "")
                        if "." in clean_val:
                            amt = float(clean_val)
                            if amt > 0:
                                amount = amt
                                break
                    except ValueError:
                        pass
                
                # Mode heuristic: scan all fields for keywords
                # Priority order matches GEMINI.md
                row_str = " ".join(row_data).upper()
                if "ADV" in row_str: mode = "ADVANCE"
                elif "BAL" in row_str: mode = "BALANCE"
                elif "CASH" in row_str: mode = "CASH"
                elif "CARD" in row_str: mode = "CARD"
                elif "UPI" in row_str: mode = "UPI"
                elif "IMPS" in row_str: mode = "IMPS"
                elif "NEFT" in row_str: mode = "NEFT"
                elif "RTGS" in row_str or "CHQ" in row_str or "CHEQUE" in row_str: mode = "RTGS_OR_CHEQUE"
                elif "PURC" in row_str or "OLD" in row_str: mode = "OLD_GOLD_EXCHANGE"

                # Capture Reference (usually alpha-numeric field with slashes or length > 5)
                for val in row_data:
                    if "/" in val or (len(val) > 5 and any(char.isdigit() for char in val)):
                        if val != str(amount) and val != mode:
                            reference = val
                            break

                if amount > 0 or mode != "UNKNOWN":
                    payment_rows.append({
                        "payment_type": "COLLECTION",
                        "payment_mode": mode,
                        "amount": amount,
                        "reference": reference,
                        "row_y": y,
                        "raw_data": row_data
                    })

        output_path = os.path.join(EXPORT_BASE, "JSON", "payment_detail_full_dump.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "form_title": payment_form.window_text(),
                "payment_rows": payment_rows
            }, f, indent=4)
        
        # Also maintain compatibility with previous JSON name if needed
        with open(JSON_OUT, "w", encoding="utf-8") as f:
             json.dump({"payment_rows": payment_rows}, f, indent=4)

        logger.info(f"Extracted {len(payment_rows)} payment rows.")
        return payment_rows

    except Exception as e:
        logger.exception("Error in Payment Extractor")
        return None

if __name__ == "__main__":
    rows = extract_payment_details()
    if rows is not None:
        print(f"Success: Extracted {len(rows)} payment rows using spatial grouping.")
    else:
        print("Failed to extract payment details.")
