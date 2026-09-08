import os
import json
import logging
import sys
from datetime import datetime
from pywinauto import Desktop, Application

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
JSON_OUT = os.path.join(EXPORT_BASE, "JSON", "prime_single_invoice_probe.json")
LOG_OUT = os.path.join(EXPORT_BASE, "Logs", "prime_single_invoice_probe.log")
CONTROLS_OUT = os.path.join(EXPORT_BASE, "Logs", "prime_single_invoice_controls.txt")

# Ensure directories exist
for path in [JSON_OUT, LOG_OUT, CONTROLS_OUT]:
    os.makedirs(os.path.dirname(path), exist_ok=True)

# Setup Logging
logging.basicConfig(
    filename=LOG_OUT,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    filemode="w"
)
logger = logging.getLogger(__name__)

def probe_prime():
    logger.info("Starting Prime single invoice probe")
    
    try:
        # Connect to Desktop to find the window
        # We look for a window title containing "SHREE ARADHANA JEWELLERS"
        # We ignore Command Prompt windows (which might have the script name in the title)
        desktop = Desktop(backend="win32")
        
        prime_window = None
        for win in desktop.windows():
            title = win.window_text()
            if "SHREE ARADHANA JEWELLERS" in title:
                # Basic check to avoid script's own window if it happens to contain the title
                if "scripts" in title.lower() or "cmd.exe" in title.lower() or "powershell" in title.lower():
                    continue
                prime_window = win
                break
        
        if not prime_window:
            msg = "Prime window ('SHREE ARADHANA JEWELLERS') not found."
            logger.error(msg)
            print(msg)
            return

        logger.info(f"Connected to Prime window: {prime_window.window_text()}")
        
        # Find ThunderRT6MDIForm
        mdi_form = None
        try:
            mdi_form = prime_window.child_window(class_name="ThunderRT6MDIForm")
            if not mdi_form.exists():
                 mdi_form = None
        except Exception:
            mdi_form = None

        if not mdi_form:
            # Fallback: maybe the main window IS the form or it's a direct child
            mdi_form = prime_window

        # Extract Controls
        text_boxes = mdi_form.descendants(class_name="ThunderRT6TextBox")
        buttons = mdi_form.descendants(class_name="ThunderRT6CommandButton")
        
        probe_data = {
            "timestamp": datetime.now().isoformat(),
            "window_title": prime_window.window_text(),
            "invoice_no": None,
            "invoice_total": 0.0,
            "payment_rows": [],
            "payment_summary": {},
            "payment_status": "GREEN",
            "reason": None,
            "extracted": {
                "customer": [],
                "amounts": []
            },
            "raw_text_boxes": []
        }

        # Control Dump and Preliminary Extraction
        with open(CONTROLS_OUT, "w", encoding="utf-8") as f:
            f.write(f"Prime Control Dump - {datetime.now()}\n")
            f.write("="*50 + "\n\n")
            
            f.write("TEXT BOXES:\n")
            for i, tb in enumerate(text_boxes):
                val = tb.window_text().strip()
                probe_data["raw_text_boxes"].append({"index": i, "value": val})
                f.write(f"[{i}] {val}\n")
                
                # Invoice No - Index 25
                if i == 25 or "/2026/" in val:
                    probe_data["invoice_no"] = val
                
                # Invoice Total - Index 29
                if i == 29:
                    try:
                        probe_data["invoice_total"] = float(val.replace(",", ""))
                    except ValueError:
                        pass

                # Customer/Mob Heuristics
                if "Mob." in val or (len(val) > 3 and val[0].isalpha() and any(char.isdigit() for char in val) and i < 25):
                    probe_data["extracted"]["customer"].append(val)
                
                # Capture all decimal-looking values for debug
                try:
                    clean_val = val.replace(",", "")
                    if "." in clean_val:
                        float(clean_val)
                        probe_data["extracted"]["amounts"].append(clean_val)
                except ValueError:
                    pass

        # Payment Row Extraction (Indices 30-33 and others potentially)
        # Based on GEMINI.md, we need to handle multiple rows.
        # For this version, we map identified indices and handle empty/unknowns.
        
        potential_payment_fields = [
            {"index": 30, "default_mode": "ADVANCE"},
            {"index": 31, "default_mode": "CASH"},
            {"index": 32, "default_mode": "BANK"}, # Generic Bank/UPI/NEFT
            {"index": 33, "default_mode": "CARD"}
        ]

        for field in potential_payment_fields:
            idx = field["index"]
            if idx < len(text_boxes):
                val = text_boxes[idx].window_text().strip()
                if val:
                    try:
                        amt = float(val.replace(",", ""))
                        if amt != 0:
                            mode = field["default_mode"]
                            # Refine mode if value or context suggests otherwise (e.g. "S" was found in index 33)
                            if mode == "CARD" and val == "S":
                                continue # Skip non-numeric markers
                            
                            row = {
                                "payment_type": "COLLECTION",
                                "payment_mode": mode,
                                "amount": amt,
                                "reference": "",
                                "bank_name": "",
                                "narration": f"Extracted from Index {idx}"
                            }
                            probe_data["payment_rows"].append(row)
                    except ValueError:
                        pass

        # Build Payment Summary
        summary = {}
        total_payments = 0.0
        for row in probe_data["payment_rows"]:
            mode = row["payment_mode"]
            amt = row["amount"]
            summary[mode] = summary.get(mode, 0.0) + amt
            total_payments += amt
        
        probe_data["payment_summary"] = summary

        # Validation
        if abs(probe_data["invoice_total"] - total_payments) > 0.01:
            probe_data["payment_status"] = "RED"
            probe_data["reason"] = "PAYMENT_TOTAL_MISMATCH"
            logger.warning(f"Validation Failed: Total={probe_data['invoice_total']}, Payments={total_payments}")
        else:
            logger.info(f"Validation Success: Total={probe_data['invoice_total']}")

        # Complete Control Dump
        with open(CONTROLS_OUT, "a", encoding="utf-8") as f:
            f.write("\nCOMMAND BUTTONS:\n")
            for i, btn in enumerate(buttons):
                txt = btn.window_text()
                f.write(f"[{i}] {txt}\n")

        # Save JSON
        with open(JSON_OUT, "w", encoding="utf-8") as f:
            json.dump(probe_data, f, indent=4)
        
        logger.info(f"Probe complete. Data saved to {JSON_OUT}")
        print(f"Success: Probe data saved to {JSON_OUT}")
        print(f"Controls dumped to {CONTROLS_OUT}")

    except Exception as e:
        logger.exception("An error occurred during probing")
        print(f"Error: {e}")

if __name__ == "__main__":
    probe_prime()
