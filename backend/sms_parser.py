import re
import logging
from typing import Dict, Optional

logger = logging.getLogger("SMS_Parser")

from backend.schemas import ParsedBankSMS


def detect_credit_or_debit(body: str) -> Optional[str]:
    """Classify a bank transaction without treating unknown messages as money in."""
    text = (body or "").upper()
    if re.search(r"\b(DEBIT(?:ED)?|WITHDRAWN|SPENT|PAID|PURCHASED)\b", text):
        return "DEBIT"
    if re.search(r"\b(CREDIT(?:ED)?|RECEIVED|DEPOSITED)\b", text):
        return "CREDIT"
    return None


def extract_payment_mode(body: str) -> Optional[str]:
    text = (body or "").upper()
    for mode in ("UPI", "IMPS", "NEFT", "RTGS", "NACH", "ECS", "CHEQUE", "ATM", "POS", "CARD", "NET BANKING", "CASH"):
        if mode in text:
            return mode
    return None


def extract_account_display(body: str) -> Optional[str]:
    """Return only the account/customer identifier printed by the bank SMS."""
    match = re.search(
        r"(?:A/?C(?:COUNT)?|ACCT|CARD|CUST(?:OMER)?\s*ID)\s*(?:NO\.?|NUMBER)?\s*[:#-]?\s*([X*\d][X*\d\s-]{2,})",
        body or "",
        re.IGNORECASE,
    )
    if not match:
        return None
    return re.sub(r"\s+", "", match.group(1)).strip("-:") or None


def extract_counterparty(body: str, direction: str) -> Optional[str]:
    """Best-effort counterparty from common Indian bank SMS templates."""
    labels = r"(?:from|by|remitter|sender)" if direction == "CREDIT" else r"(?:to|at|merchant|beneficiary|towards|by)"
    match = re.search(
        rf"\b{labels}\b\s*[:.-]?\s*([^\n.;]{2,80})",
        body or "",
        re.IGNORECASE,
    )
    if not match:
        return None
    candidate = re.sub(r"\s+", " ", match.group(1)).strip(" -:.")
    return candidate or None

def parse_bank_sms(body: str) -> ParsedBankSMS:
    """
    Deterministic regex parser for bank SMS alerts.
    Returns ParsedBankSMS Pydantic model.
    """
    amount = None
    utr_reference = None
    transaction_date = None
    sender_bank = None
    payer_name = None
    account_suffix = None
    confidence = "LOW"
    
    body_upper = body.upper()
    
    # 1. ICICI Forwarder Format (Exact user requirement)
    # Account\s+(\d+).*?credited\s+with\s+Rs\s+([\d,]+\.\d+|\d+).*?on\s+(\d{4}-\d{2}-\d{2})\s+at\s+(\d{2}:\d{2}:\d{2}).*?from\s+(.*?)\.\s*Ref\s+No\s+([A-Za-z0-9]+)
    icici_match = re.search(r"Account\s+(\d+).*?credited\s+with\s+Rs\s+([\d,]+\.\d+|\d+).*?on\s+(\d{4}-\d{2}-\d{2})\s+at\s+(\d{2}:\d{2}:\d{2}).*?from\s+(.*?)\.\s*Ref\s+No\s+([A-Za-z0-9]+)", body, re.IGNORECASE | re.DOTALL)
    if icici_match:
        account_suffix = icici_match.group(1)
        amount = float(icici_match.group(2).replace(",", ""))
        transaction_date = f"{icici_match.group(3)} {icici_match.group(4)}"
        payer_name = icici_match.group(5).strip()
        utr_reference = icici_match.group(6)
        sender_bank = "ICICI"
        confidence = "HIGH"
        
    # 2. General Formats (Fallback)
    if not icici_match:
        # Amount
        amt_match = re.search(r"(?:INR|RS\.?)\s*([\d,]+\.?\d*)", body, re.IGNORECASE)
        if amt_match:
            amount = float(amt_match.group(1).replace(",", ""))
                
        # UTR / Reference
        utr_match = re.search(r"(?:UPI Ref[:\s]*|Ref No[:\s]*|UTR Number[:\s]*|UTR[:\s]*|Ref[:\s]*)(\w+)", body, re.IGNORECASE)
        if utr_match:
            utr_reference = utr_match.group(1)
        else:
            upi_match = re.search(r"\b(\d{12})\b", body)
            if upi_match:
                utr_reference = upi_match.group(1)

        # Date
        date_match = re.search(r"(\d{2}[-/]\d{2}[-/]\d{4}|\d{2}\s\w{3}\s\d{4})", body)
        if date_match:
            transaction_date = date_match.group(1)
            
        # Bank Name
        if "SBI" in body_upper: sender_bank = "SBI"
        elif "HDFC" in body_upper: sender_bank = "HDFC"
        elif "ICICI" in body_upper: sender_bank = "ICICI"
        elif "AXIS" in body_upper: sender_bank = "AXIS"
        elif "KOTAK" in body_upper: sender_bank = "KOTAK"

        # Confidence Scoring for Fallback
        if amount and transaction_date and sender_bank and utr_reference:
            confidence = "HIGH"
        elif amount and transaction_date and sender_bank:
            confidence = "MEDIUM"
        elif amount:
            confidence = "LOW"

    return ParsedBankSMS(
        amount=amount,
        utr_reference=utr_reference,
        transaction_date=transaction_date,
        sender_bank=sender_bank,
        raw_message=body,
        payer_name=payer_name,
        account_suffix=account_suffix,
        confidence=confidence
    )

def parse_sms_body(body: str):
    """Legacy alias for backward compatibility with pollers"""
    parsed = parse_bank_sms(body)
    return {
        "bank_name": parsed.sender_bank or "UNKNOWN",
        "account_suffix": parsed.account_suffix,
        "credit_or_debit": detect_credit_or_debit(body),
        "amount": parsed.amount or 0.0,
        "utr_reference": parsed.utr_reference,
        "payer_name": parsed.payer_name,
        "transaction_date": parsed.transaction_date,
        "confidence": parsed.confidence
    }
