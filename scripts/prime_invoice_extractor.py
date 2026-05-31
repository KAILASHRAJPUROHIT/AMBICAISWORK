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

def find_nearest_textbox(parent, anchor_text):
    """
    Finds the ThunderRT6TextBox closest to a label control with anchor_text.
    Labels in Prime are often ThunderRT6CommandButton or Static.
    """
    # 1. Find the anchor (label)
    anchors = []
    # Search all descendants for the text
    for ctrl in parent.descendants():
        if anchor_text.lower() in ctrl.window_text().lower():
            anchors.append(ctrl)
    
    if not anchors:
        logger.warning(f"Anchor '{anchor_text}' not found.")
        return None

    # Use the first match (usually labels are unique enough in a form scope)
    anchor = anchors[0]
    anchor_rect = anchor.rectangle()
    logger.info(f"Anchor '{anchor_text}' found at {anchor_rect}")

    # 2. Find all candidates (textboxes)
    candidates = parent.descendants(class_name="ThunderRT6TextBox")
    
    best_match = None
    min_dist = float('inf')

    for cand in candidates:
        cand_rect = cand.rectangle()
        
        # Heuristic: Check if the candidate is to the right or below the anchor
        # Horizontal distance (tb.left - anchor.right)
        # Vertical distance (tb.top - anchor.top)
        
        dx = max(0, cand_rect.left - anchor_rect.right)
        dy = abs(cand_rect.top - anchor_rect.top)
        
        # Total distance - weighting horizontal proximity as VB6 labels are mostly on the left
        dist = (dx**2 + (dy * 2)**2)**0.5 
        
        if dist < min_dist:
            min_dist = dist
            best_match = cand

    if best_match:
        logger.info(f"Matched '{anchor_text}' to textbox at {best_match.rectangle()} with distance {min_dist:.2f}")
        return {
            "value": best_match.window_text().strip(),
            "rect": str(best_match.rectangle()),
            "class": best_match.class_name(),
            "anchor": anchor_text,
            "anchor_rect": str(anchor_rect)
        }
    
    return None

def extract_invoice_header():
    logger.info("Starting Anchor-Based Invoice Header Extraction")
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

        # 1. Identify active form
        bill_form = None
        for child in prime_window.descendants(class_name="ThunderRT6FormDC"):
            txt = child.window_text()
            if "Bill" in txt and "Payment Detail" not in txt:
                bill_form = child
                break
        
        if not bill_form:
            logger.warning("No specific bill form detected, falling back to MDI.")
            bill_form = prime_window

        logger.info(f"Targeting Form: {bill_form.window_text()}")

        # 2. Define anchors
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
            result = find_nearest_textbox(bill_form, label)
            if result:
                invoice_data["fields"][key] = result["value"]
                invoice_data["audit_evidence"].append(result)
                extracted_count += 1
            else:
                invoice_data["fields"][key] = None

        # 3. Validation
        status = "GREEN"
        if not invoice_data["fields"].get("invoice_no") or not invoice_data["fields"].get("customer_name"):
            status = "EXTRACTION_FAILED"
            logger.error("Mandatory fields missing.")

        invoice_data["status"] = status

        with open(JSON_OUT, "w", encoding="utf-8") as f:
            json.dump(invoice_data, f, indent=4)
        
        logger.info(f"Extraction finished. Success rate: {extracted_count}/{len(anchors)}")
        return invoice_data

    except Exception as e:
        logger.exception("Error in Anchor-Based Extractor")
        return None

if __name__ == "__main__":
    data = extract_invoice_header()
    if data:
        print(f"Success: Extracted invoice {data['fields'].get('invoice_no')} using anchor strategy.")
    else:
        print("Failed to extract invoice.")
