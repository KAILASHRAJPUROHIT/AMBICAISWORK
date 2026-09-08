import re
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

class ICICITemplateParser:
    """Deterministic parser for ICICI Bank email templates based on discovery."""

    def strip_html(self, html: str) -> str:
        if not html: return ""
        # Remove script and style elements
        clean = re.sub(r'<(script|style).*?>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # Remove remaining tags
        clean = re.sub(r'<.*?>', ' ', clean)
        # Normalize whitespace
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def parse(self, subject: str, raw_body: str) -> Dict[str, Any]:
        """
        Routes parsing to specific template logic based on subject signature.
        """
        cleaned_text = self.strip_html(raw_body)
        subject_up = subject.upper()
        
        # 1. Template: Merchant Statement (MPR)
        if "MERCHANTSTATEMENT" in subject_up:
            return self._parse_merchant_statement(subject, cleaned_text)
            
        # 2. Template: Service Request Status
        if "STATUS OF YOUR" in subject_up:
            return self._parse_service_request(subject, cleaned_text)
            
        # 3. Template: Transaction Alert (Credit/Debit)
        if "CREDITED" in cleaned_text.upper() or "DEBITED" in cleaned_text.upper():
            return self._parse_transaction_alert(subject, cleaned_text)

        # 4. Template: OTP or Security
        if "OTP" in subject_up or "PASSWORD" in subject_up:
            return {
                "template": "SECURITY_ALERT",
                "is_transaction": False,
                "status": "NON_FINANCIAL"
            }

        # 5. Default
        return {
            "template": "UNKNOWN_FORMAT",
            "is_transaction": False,
            "status": "FAILED",
            "raw_text_snippet": cleaned_text[:200]
        }

    def _parse_merchant_statement(self, subject: str, text: str) -> Dict[str, Any]:
        return {
            "template": "MERCHANT_STATEMENT",
            "is_transaction": False,
            "subject": subject,
            "status": "NON_FINANCIAL",
            "message": "MPR Statement attachment notification."
        }

    def _parse_service_request(self, subject: str, text: str) -> Dict[str, Any]:
        return {
            "template": "SERVICE_REQUEST",
            "is_transaction": False,
            "status": "NON_FINANCIAL",
            "message": "Terminal or service request update."
        }

    def _parse_transaction_alert(self, subject: str, text: str) -> Dict[str, Any]:
        """
        Extracts financial details from ICICI Credit/Debit alerts.
        """
        # Patterns for amount and UTR
        re_amount = re.compile(r"(?:INR|Rs\.?)\s*([\d,]+\.\d{2}|[\d,]+)", re.IGNORECASE)
        re_date = re.compile(r"(\d{1,2}[-/\s][A-Za-z]{3,9}[-/\s]\d{2,4}|\d{1,2}[-/\s]\d{1,2}[-/\s]\d{2,4})")
        
        amt_match = re_amount.search(text)
        date_match = re_date.search(text)
        
        # Look for UTR in 'Info' string patterns (e.g. UPI/UTR/NAME or INF/NEFT/UTR/NAME)
        utr = None
        mode = "UNKNOWN"
        sender = None
        
        # ICICI common patterns
        if "UPI/" in text:
            mode = "UPI"
            m = re.search(r"UPI/(\d{12})/([^/]+)", text, re.IGNORECASE)
            if m: utr, sender = m.group(1), m.group(2).strip()
        elif "NEFT/" in text:
            mode = "NEFT"
            m = re.search(r"INF/NEFT/([A-Z0-9]+)/([^/]+)", text, re.IGNORECASE)
            if m: utr, sender = m.group(1), m.group(2).strip()
        elif "IMPS/" in text:
            mode = "IMPS"
            m = re.search(r"INF/IMPS/(\d+)/([^/]+)", text, re.IGNORECASE)
            if m: utr, sender = m.group(1), m.group(2).strip()
                
        if not utr:
            # General fallback for UTR/Reference
            utr_gen = re.search(r"(?:UTR|Ref|Reference)[:\s\-]+([A-Z0-9]{8,22})", text, re.IGNORECASE)
            if utr_gen: utr = utr_gen.group(1)

        is_trans = bool(amt_match and utr)
        
        return {
            "template": "TRANSACTION_ALERT",
            "is_transaction": is_trans,
            "amount": float(amt_match.group(1).replace(",", "")) if amt_match else 0.0,
            "transaction_date": date_match.group(1) if date_match else None,
            "utr": utr,
            "sender_name": sender,
            "mode": mode,
            "credit_or_debit": "CREDIT" if "CREDITED" in text.upper() else "DEBIT",
            "status": "PARSED" if is_trans else "NEEDS_REVIEW"
        }
