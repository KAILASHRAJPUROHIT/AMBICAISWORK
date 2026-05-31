import os
import json
import logging
from datetime import datetime
from pywinauto import Desktop

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
JSON_OUT = os.path.join(EXPORT_BASE, "JSON", "raw_payment_rows.json")
LOG_OUT = os.path.join(EXPORT_BASE, "Logs", "payment_extractor.log")

# Ensure directories
os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
os.makedirs(os.path.dirname(LOG_OUT), exist_ok=True)

logging.basicConfig(filename=LOG_OUT, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def extract_payment_details():
    logger.info("Starting Payment Detail Extraction")
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
        
        # Extract all textboxes
        tbs = payment_form.descendants(class_name="ThunderRT6TextBox")
        
        # VB6 grids often flatten controls. We need to group them.
        # Based on the diff probe, a payment row likely consists of:
        # [Mode Code, Mode Name, Amount, Ref, Bank, Narration]
        # We'll use a stride-based approach or look for numeric amounts.
        
        payment_rows = []
        raw_values = [tb.window_text().strip() for tb in tbs]
        
        # Heuristic: Find rows by looking for payment mode keywords or numeric amounts
        # For MVP, we'll capture everything and the user can refine indices.
        # We assume a stride of 6-8 based on typical VB6 accounting layouts.
        stride = 10 # Conservative estimate based on the large number of controls seen
        
        for i in range(0, len(raw_values), stride):
            row_slice = raw_values[i:i+stride]
            if any(row_slice): # If any field in row has data
                # Identify amount (usually the first decimal-looking field)
                amount = 0.0
                mode = "UNKNOWN"
                for val in row_slice:
                    try:
                        clean_val = val.replace(",", "")
                        if "." in clean_val and float(clean_val) != 0:
                            amount = float(clean_val)
                            break
                    except ValueError:
                        pass
                
                # Identify mode (CASH, BANK, ADV, etc)
                for val in row_slice:
                    val_up = val.upper()
                    if any(k in val_up for k in ["CASH", "BANK", "UPI", "CARD", "ADV", "NEFT", "IMPS", "RTGS", "CHQ", "OLD"]):
                        mode = val_up
                        break
                
                if amount > 0 or mode != "UNKNOWN":
                    payment_rows.append({
                        "payment_type": "COLLECTION",
                        "payment_mode": mode,
                        "amount": amount,
                        "raw_data": row_slice
                    })

        with open(JSON_OUT, "w", encoding="utf-8") as f:
            json.dump({"timestamp": datetime.now().isoformat(), "payment_rows": payment_rows}, f, indent=4)
        
        logger.info(f"Extracted {len(payment_rows)} payment rows.")
        return payment_rows

    except Exception as e:
        logger.exception("Error in Payment Extractor")
        return None

if __name__ == "__main__":
    rows = extract_payment_details()
    if rows is not None:
        print(f"Success: Extracted {len(rows)} payment rows to {JSON_OUT}")
    else:
        print("Failed to extract payment details.")
