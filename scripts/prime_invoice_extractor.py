import os
import json
import logging
from datetime import datetime
from pywinauto import Desktop

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
JSON_OUT = os.path.join(EXPORT_BASE, "JSON", "raw_invoice.json")
LOG_OUT = os.path.join(EXPORT_BASE, "Logs", "invoice_extractor.log")

os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
os.makedirs(os.path.dirname(LOG_OUT), exist_ok=True)

logging.basicConfig(filename=LOG_OUT, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def find_nearest_textbox_in_form(target_form, anchor_text, prime_window):
    """
    Finds the ThunderRT6TextBox within target_form closest to an anchor label 
    that might be anywhere in the process windows.
    """
    # 1. Search for anchor in all process windows
    anchors = []
    process_pids = [prime_window.process_id()]
    desktop = Desktop(backend="win32")
    
    for win in desktop.windows():
        try:
            if win.process_id() not in process_pids:
                continue
            for ctrl in win.descendants():
                if anchor_text.lower() in ctrl.window_text().lower():
                    anchors.append(ctrl)
        except Exception:
            continue
    
    if not anchors:
        logger.warning(f"Anchor '{anchor_text}' not found anywhere in process.")
        return None

    # Use the first match
    anchor = anchors[0]
    anchor_rect = anchor.rectangle()

    # 2. Search for textboxes ONLY in the target form
    candidates = target_form.descendants(class_name="ThunderRT6TextBox")
    
    best_match = None
    min_dist = float('inf')

    for cand in candidates:
        cand_rect = cand.rectangle()
        
        # RULE 1: Vertical alignment (mostly)
        dy = abs(cand_rect.top - anchor_rect.top)
        if dy > 50: # Slightly more lenient for MDI offsets
            continue
            
        # RULE 2: Horizontal alignment (mostly right)
        dx = cand_rect.left - anchor_rect.right
        
        # We allow small negative dx (overlap) but prefer positive
        dist = abs(dx) + (dy * 5)
        
        if dist < min_dist:
            min_dist = dist
            best_match = cand

    if best_match:
        return {
            "value": best_match.window_text().strip(),
            "rect": str(best_match.rectangle()),
            "class": best_match.class_name(),
            "anchor": anchor_text,
            "anchor_rect": str(anchor_rect)
        }
    
    return None

def extract_invoice_header():
    logger.info("Starting Refined Anchor-Based Invoice Header Extraction")
    try:
        desktop = Desktop(backend="win32")
        prime_window = None
        for win in desktop.windows():
            title = win.window_text().upper()
            if "SHREE ARADHANA" in title or "FA" == title or "JEWELLERS" in title:
                if "VSCODE" in title or "PYTHON" in title or "CMD.EXE" in title:
                    continue
                prime_window = win
                break
        
        if not prime_window:
            logger.error("Prime window not found.")
            return {"status": "EXTRACTION_FAILED", "reason": "PRIME_WINDOW_NOT_FOUND"}

        # 1. Identify active form
        # For MDI, just find the first visible Sales Bill form
        bill_form = None
        for win in desktop.windows():
            try:
                if win.process_id() != prime_window.process_id(): continue
                for f in win.descendants(class_name="ThunderRT6FormDC"):
                    txt = f.window_text().strip()
                    if "Sales Bill" in txt and "Payment Detail" not in txt:
                        bill_form = f
                        break
                if bill_form: break
            except Exception: continue
            
        if not bill_form:
            logger.error("No valid Sales Bill form found.")
            return {"status": "EXTRACTION_FAILED", "reason": "NO_VALID_FORM_FOUND"}

        logger.info(f"Targeting Form: {bill_form.window_text()} [Handle: {bill_form.handle}]")

        # 2. Visibility Guard
        if prime_window.is_minimized():
            prime_window.restore()
            prime_window.set_focus()
            import time
            time.sleep(1)

        # 3. Define anchors
        anchors = {
            "invoice_no": "Vch.No.",
            "invoice_date": "Date >",
            "customer_code": "A/c Code",
            "customer_name": "A/c Name",
            "invoice_total": "Invoice Amount",
            "taxable_amount": "Taxable",
            "cgst": "CGST",
            "sgst": "SGST"
        }

        invoice_data = {
            "timestamp": datetime.now().isoformat(),
            "form_title": bill_form.window_text(),
            "fields": {},
            "audit_evidence": []
        }

        extracted_count = 0
        for key, label in anchors.items():
            result = find_nearest_textbox_in_form(bill_form, label, prime_window)
            if result:
                invoice_data["fields"][key] = result["value"]
                invoice_data["audit_evidence"].append(result)
                extracted_count += 1
            else:
                invoice_data["fields"][key] = None

        # 4. Validation
        status = "GREEN"
        reason = None
        if not invoice_data["fields"].get("invoice_no") or not invoice_data["fields"].get("customer_name"):
            status = "EXTRACTION_FAILED"
            reason = "MANDATORY_FIELDS_MISSING"

        invoice_data["status"] = status
        invoice_data["reason"] = reason

        with open(JSON_OUT, "w", encoding="utf-8") as f:
            json.dump(invoice_data, f, indent=4)
        
        logger.info(f"Extraction finished. Success rate: {extracted_count}/{len(anchors)}")
        return invoice_data

    except Exception as e:
        logger.exception("Error in Refined Anchor-Based Extractor")
        return None

    except Exception as e:
        logger.exception("Error in Refined Anchor-Based Extractor")
        return None

if __name__ == "__main__":
    data = extract_invoice_header()
    if data and data.get("status") == "GREEN":
        print(f"Success: Extracted invoice {data['fields'].get('invoice_no')} using anchor strategy.")
    elif data:
        print(f"Extraction Failed: {data.get('reason')}")
    else:
        print("Failed to extract invoice.")
