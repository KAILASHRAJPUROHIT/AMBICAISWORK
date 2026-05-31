import os
import json
import logging
from datetime import datetime
from pywinauto import Desktop

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
JSON_OUT = os.path.join(EXPORT_BASE, "JSON", "raw_payment_rows.json")
LOG_OUT = os.path.join(EXPORT_BASE, "Logs", "payment_extractor.log")

os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
os.makedirs(os.path.dirname(LOG_OUT), exist_ok=True)

logging.basicConfig(filename=LOG_OUT, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def extract_payment_details():
    logger.info("Starting Anchor-Based Payment Detail Extraction")
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

        # Find the Payment Detail sub-form
        payment_form = None
        for child in prime_window.descendants(class_name="ThunderRT6FormDC"):
            if "Payment Detail" in child.window_text():
                payment_form = child
                break
        
        if not payment_form:
            logger.warning("Payment Detail form not visible.")
            return []

        logger.info(f"Found Payment Detail Form: {payment_form.window_text()}")
        
        # 1. Identify Header Anchors
        # In the grid, headers like "A/c Name", "Amount", "ChqNo." help define columns
        header_texts = ["A/c Name", "Amount", "ChqNo.", "Due Date", "Drawn On", "Card Amt."]
        headers = {}
        for text in header_texts:
            for ctrl in payment_form.descendants():
                if text.lower() in ctrl.window_text().lower():
                    headers[text] = ctrl.rectangle()
                    break

        # 2. Extract all textboxes and group by row (Y-coordinate proximity)
        tbs = payment_form.descendants(class_name="ThunderRT6TextBox")
        
        rows = {}
        for tb in tbs:
            rect = tb.rectangle()
            # Group by rounding Y-coordinate to nearest 5 or 10 pixels
            y_key = round(rect.top / 10) * 10
            if y_key not in rows:
                rows[y_key] = []
            rows[y_key].append(tb)

        payment_rows = []
        # Sort rows by Y-coordinate
        for y in sorted(rows.keys()):
            row_ctrls = sorted(rows[y], key=lambda c: c.rectangle().left)
            row_data = [c.window_text().strip() for c in row_ctrls]
            
            if any(row_data):
                # Identify amount and mode from the row
                amount = 0.0
                mode = "UNKNOWN"
                
                # Heuristic for MVP: amount is usually a non-zero decimal
                for val in row_data:
                    try:
                        clean_val = val.replace(",", "")
                        if "." in clean_val and float(clean_val) != 0:
                            amount = float(clean_val)
                            break
                    except ValueError:
                        pass
                
                # Mode heuristic: look for keywords in the row data
                for val in row_data:
                    v_up = val.upper()
                    if any(k in v_up for k in ["CASH", "BANK", "UPI", "CARD", "ADV", "NEFT", "IMPS", "RTGS", "CHQ", "OLD"]):
                        mode = v_up
                        break
                
                if amount > 0 or mode != "UNKNOWN":
                    payment_rows.append({
                        "payment_type": "COLLECTION",
                        "payment_mode": mode,
                        "amount": amount,
                        "row_y": y,
                        "raw_data": row_data,
                        "audit_evidence": {
                            "rects": [str(c.rectangle()) for c in row_ctrls]
                        }
                    })

        with open(JSON_OUT, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "form_title": payment_form.window_text(),
                "payment_rows": payment_rows
            }, f, indent=4)
        
        logger.info(f"Extracted {len(payment_rows)} payment rows using Y-grouping anchor.")
        return payment_rows

    except Exception as e:
        logger.exception("Error in Anchor-Based Payment Extractor")
        return None

if __name__ == "__main__":
    rows = extract_payment_details()
    if rows is not None:
        print(f"Success: Extracted {len(rows)} payment rows using spatial grouping.")
    else:
        print("Failed to extract payment details.")
