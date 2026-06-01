import re
import logging
from typing import Dict, Optional

logger = logging.getLogger("SMS_Parser")

from backend.schemas import ParsedBankSMS

def parse_bank_sms(body: str) -> ParsedBankSMS:
    """
    Deterministic regex parser for bank SMS alerts.
    Returns ParsedBankSMS Pydantic model.
    """
    amount = None
    utr_reference = None
    transaction_date = None
    sender_bank = None
    
    body_upper = body.upper()
    
    # 1. Amount
    amt_match = re.search(r"(?:INR|RS\.?)\s*([\d,]+\.?\d*)", body, re.IGNORECASE)
    if amt_match:
        val = amt_match.group(1).replace(",", "")
        if "." in val:
            amount = float(val)
        else:
            amount = float(val)
            
    # 2. UTR / Reference
    utr_match = re.search(r"(?:UPI Ref[:\s]*|Ref No[:\s]*|UTR Number[:\s]*|UTR[:\s]*|Ref[:\s]*)(\w+)", body, re.IGNORECASE)
    if utr_match:
        utr_reference = utr_match.group(1)
    else:
        upi_match = re.search(r"\b(\d{12})\b", body)
        if upi_match:
            utr_reference = upi_match.group(1)

    # 3. Date
    date_match = re.search(r"(\d{2}[-/]\d{2}[-/]\d{4}|\d{2}\s\w{3}\s\d{4})", body)
    if date_match:
        transaction_date = date_match.group(1)
        
    # 4. Bank Name
    if "SBI" in body_upper: sender_bank = "SBI"
    elif "HDFC" in body_upper: sender_bank = "HDFC"
    elif "ICICI" in body_upper: sender_bank = "ICICI"
    elif "AXIS" in body_upper: sender_bank = "AXIS"
    elif "KOTAK" in body_upper: sender_bank = "KOTAK"

    return ParsedBankSMS(
        amount=amount,
        utr_reference=utr_reference,
        transaction_date=transaction_date,
        sender_bank=sender_bank,
        raw_message=body
    )

def parse_sms_body(body: str):
    """Legacy alias for backward compatibility with pollers"""
    parsed = parse_bank_sms(body)
    return {
        "bank_name": parsed.sender_bank or "UNKNOWN",
        "account_suffix": None, # TBD
        "credit_or_debit": "CREDIT" if any(x in body.upper() for x in ["CREDITED", "RECEIVED", "DEPOSITED"]) else "DEBIT",
        "amount": parsed.amount or 0.0,
        "utr_reference": parsed.utr_reference,
        "parsed_confidence": 0.8 if parsed.amount and parsed.utr_reference else 0.4
    }
