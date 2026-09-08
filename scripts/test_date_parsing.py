import re
from datetime import datetime

def parse_dates(text):
    data = {
        "invoice_date": None,
        "order_date": None
    }
    
    # Strictly look for "Date: DD/MM/YYYY" as invoice date
    # Usually it's on a line starting with "Date:" or follows "Invoice No"
    invoice_date_match = re.search(r"\bDate\s*:\s*(\d{2}[-/]\d{2}[-/]\d{4})", text)
    if invoice_date_match:
        try:
            data["invoice_date"] = datetime.strptime(invoice_date_match.group(1).replace("/", "-"), "%d-%m-%Y")
        except: pass

    # Look for bracketed dates or C.O.No. dates as order dates
    order_date_matches = re.findall(r"(?:C\.O\.No\.|RO-|P2-).*?(\d{2}[-/]\d{2}[-/]\d{4})", text)
    if not order_date_matches:
        # Try bracketed dates
        order_date_matches = re.findall(r"\((\d{2}[-/]\d{2}[-/]\d{4})\)", text)
        
    if order_date_matches:
        try:
            # Pick the first one that is NOT the invoice date
            for d_str in order_date_matches:
                d_val = datetime.strptime(d_str.replace("/", "-"), "%d-%m-%Y")
                if d_val != data["invoice_date"]:
                    data["order_date"] = d_val
                    break
            # Fallback to first if only one found and it happens to be same
            if not data["order_date"] and order_date_matches:
                data["order_date"] = datetime.strptime(order_date_matches[0].replace("/", "-"), "%d-%m-%Y")
        except: pass
        
    return data

sample_text = """
Invoice No.: SG-889
Date: 01/06/2026
Customer: ARUNA CHAVAN
C.O.No.: RO-179 (29/05/2026)
Total 1549.00
"""

results = parse_dates(sample_text)
print(f"Parsed Results: {results}")
print(f"Invoice Date: {results['invoice_date']}")
print(f"Order Date: {results['order_date']}")
