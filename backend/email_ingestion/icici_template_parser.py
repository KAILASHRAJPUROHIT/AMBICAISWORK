import re
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

class ICICITemplateParser:
    """Deterministic parser for ICICI Bank email templates."""

    def strip_html(self, html: str) -> str:
        if not html: return ""
        clean = re.sub(r'<(script|style).*?>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r'<.*?>', ' ', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def parse(self, subject: str, raw_body: str) -> Dict[str, Any]:
        """
        Routes parsing to specific template logic based on subject signature.
        """
        cleaned_text = self.strip_html(raw_body)
        
        # 1. Template: Merchant Statement Attachment
        if "MerchantStatement" in subject:
            return self._parse_merchant_statement(subject, cleaned_text)
            
        # 2. Template: Service Request Status
        if "Status of your" in subject:
            return self._parse_service_request(subject, cleaned_text)
            
        # 3. Template: OTP
        if "OTP For Forget" in subject or "proceed for T&Cs" in cleaned_text:
            return self._parse_otp(subject, cleaned_text)

        # 4. Default: Try Transaction Alert (Fallback to broad regex)
        return self._parse_transaction_fallback(subject, cleaned_text)

    def _parse_merchant_statement(self, subject: str, text: str) -> Dict[str, Any]:
        return {
            "template": "MERCHANT_STATEMENT_ATTACHMENT",
            "is_transaction": False,
            "subject": subject,
            "status": "NON_FINANCIAL_ALERT",
            "message": "MPR Statement attachment notification. No transaction in body."
        }

    def _parse_service_request(self, subject: str, text: str) -> Dict[str, Any]:
        sr_id = re.search(r"Status of your (\d+)", subject)
        return {
            "template": "SERVICE_REQUEST_STATUS",
            "is_transaction": False,
            "sr_id": sr_id.group(1) if sr_id else None,
            "status": "NON_FINANCIAL_ALERT"
        }

    def _parse_otp(self, subject: str, text: str) -> Dict[str, Any]:
        otp_match = re.search(r"(\d{6}) is the OTP", text)
        return {
            "template": "OTP_ALERT",
            "is_transaction": False,
            "otp_found": bool(otp_match),
            "status": "SECURITY_ALERT"
        }

    def _parse_transaction_fallback(self, subject: str, text: str) -> Dict[str, Any]:
        """
        Broad regex for ICICI Credit/Debit Alerts.
        Used when no specific non-financial template matches.
        """
        # Patterns from EmailParser (standardized)
        re_amount = re.compile(r"(?:INR|Rs\.?)\s*([\d,]+\.\d{2}|[\d,]+)", re.IGNORECASE)
        re_date = re.compile(r"(\d{1,2}[-/\s][A-Za-z]{3,9}[-/\s]\d{2,4}|\d{1,2}[-/\s]\d{1,2}[-/\s]\d{2,4})")
        
        amt_match = re_amount.search(text)
        date_match = re_date.search(text)
        
        # Look for UTR in 'Info' string patterns
        utr = None
        mode = "UNKNOWN"
        sender = None
        
        if "UPI/" in text:
            mode = "UPI"
            m = re.search(r"UPI/(\d{12})/([^/]+)", text, re.IGNORECASE)
            if m:
                utr, sender = m.group(1), m.group(2).strip()
        elif "NEFT/" in text:
            mode = "NEFT"
            m = re.search(r"INF/NEFT/([A-Z0-9]+)/([^/]+)", text, re.IGNORECASE)
            if m:
                utr, sender = m.group(1), m.group(2).strip()
                
        if not utr:
            # General fallback for UTR
            utr_gen = re.search(r"(?:UTR|Ref|Reference)[:\s\-]+([A-Z0-9]{8,22})", text, re.IGNORECASE)
            if utr_gen: utr = utr_gen.group(1)

        is_trans = bool(amt_match and utr)
        
        return {
            "template": "TRANSACTION_ALERT" if is_trans else "UNKNOWN_ICICI_FORMAT",
            "is_transaction": is_trans,
            "amount": float(amt_match.group(1).replace(",", "")) if amt_match else 0.0,
            "transaction_date": date_match.group(1) if date_match else None,
            "utr": utr,
            "sender_name": sender,
            "mode": mode,
            "status": "GREEN" if is_trans else "NEEDS_REVIEW"
        }
