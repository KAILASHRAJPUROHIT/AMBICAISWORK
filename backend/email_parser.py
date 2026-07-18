import re
from typing import Optional
from backend.schemas import ParsedBankEmail

def extract_amount(text: str) -> Optional[float]:
    match = re.search(r'(?:Rs\.?|INR)\s*([\d,]+\.\d{2}|[\d,]+)', text, re.IGNORECASE)
    if match:
        amount_str = match.group(1).replace(',', '')
        try:
            return float(amount_str)
        except ValueError:
            return None
    return None

def extract_utr(text: str) -> Optional[str]:
    # Look for UTR, Ref No, Reference, etc.
    # Ref: HDFCR520231027999
    match = re.search(r'(?:UTR(?: Number| No)?|Ref(?:erence)?(?: No)?)[:\-\s]+([A-Za-z0-9]{8,22})', text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def extract_date(text: str) -> Optional[str]:
    # Formats: DD/MM/YYYY, DD-MM-YYYY, DD MMM YYYY, DD/MM/YY
    match = re.search(r'(\d{2}[/-]\d{2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', text)
    if match:
        return match.group(1)
    return None

def extract_bank(subject: str, body: str) -> Optional[str]:
    combined = (str(subject) + " " + str(body)).upper()
    if "HDFC" in combined: return "HDFC"
    if "ICICI" in combined: return "ICICI"
    if "SBI" in combined: return "SBI"
    if "STATE BANK" in combined: return "SBI"
    return None

def parse_bank_email(subject: str, body: str) -> ParsedBankEmail:
    combined_text = subject + " \n " + body
    
    return ParsedBankEmail(
        amount=extract_amount(combined_text),
        utr_reference=extract_utr(combined_text),
        transaction_date=extract_date(combined_text),
        sender_bank=extract_bank(subject, body),
        raw_subject=subject,
        raw_body=body
    )
