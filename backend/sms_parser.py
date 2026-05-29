import re
from typing import Optional
from backend.schemas import ParsedBankSMS

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
    # Look for UTR, Ref No, Reference, UPI Ref, etc.
    match = re.search(r'(?:UTR(?: Number| No)?|Ref(?:erence)? No|UPI(?: Ref)?|IMPS|NEFT)[:\-\s]+([A-Za-z0-9]{8,22})', text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def extract_date(text: str) -> Optional[str]:
    # Formats: DD/MM/YYYY, DD-MM-YYYY, DD MMM YYYY, etc.
    match = re.search(r'(\d{2}[/-]\d{2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', text)
    if match:
        return match.group(1)
    return None

def extract_bank(text: str) -> Optional[str]:
    combined = text.upper()
    if "HDFC" in combined:
        return "HDFC"
    if "ICICI" in combined:
        return "ICICI"
    if "SBI" in combined or "STATE BANK OF INDIA" in combined:
        return "SBI"
    return None

def parse_bank_sms(message: str) -> ParsedBankSMS:
    return ParsedBankSMS(
        amount=extract_amount(message),
        utr_reference=extract_utr(message),
        transaction_date=extract_date(message),
        sender_bank=extract_bank(message),
        raw_message=message
    )
