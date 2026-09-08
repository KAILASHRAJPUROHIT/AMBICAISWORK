import re
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

class UniversalTemplateParser:
    """Deterministic parser for multiple banks (ICICI, SBI, HDFC)."""

    def strip_html(self, html: str) -> str:
        if not html: return ""
        clean = re.sub(r'<(script|style).*?>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r'<.*?>', ' ', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def parse(self, subject: str, raw_body: str, label: str = "UNKNOWN") -> Dict[str, Any]:
        cleaned_text = self.strip_html(raw_body)
        subj_up = subject.upper()
        text_up = cleaned_text.upper()
        
        # 1. ICICI Templates
        if "ICICI" in label or "ICICI" in subj_up:
            if "MERCHANTSTATEMENT" in subj_up:
                return {"template": "ICICI_MPR_STATEMENT", "is_transaction": False, "status": "NON_FINANCIAL"}
            if "STATUS OF YOUR" in subj_up:
                return {"template": "ICICI_SERVICE_REQUEST", "is_transaction": False, "status": "NON_FINANCIAL"}
            if "CREDITED" in text_up or "DEBITED" in text_up:
                return self._parse_icici_transaction(cleaned_text)

        # 2. SBI Templates
        if "SBI" in label or "SBI" in subj_up:
            if "HAS A CREDIT" in text_up:
                return self._parse_sbi_credit(cleaned_text)
            if "THANK YOU FOR THE TRANSACTION" in text_up:
                return {"template": "SBI_VISIT_FEEDBACK", "is_transaction": False, "status": "NON_FINANCIAL"}

        # 3. HDFC Templates
        if "HDFC" in label or "HDFC" in subj_up:
            if "MONTHLY GST INVOICE" in text_up:
                return {"template": "HDFC_GST_INVOICE", "is_transaction": False, "status": "NON_FINANCIAL"}

        # 4. Fallback for any Credit/Debit
        if "CREDITED" in text_up or "HAS A CREDIT" in text_up:
            return self._parse_generic_credit(cleaned_text)

        return {
            "template": "UNKNOWN_FORMAT",
            "is_transaction": False,
            "status": "FAILED",
            "raw_text_snippet": cleaned_text[:200]
        }

    def _parse_icici_transaction(self, text: str) -> Dict[str, Any]:
        re_amount = re.compile(r"(?:INR|Rs\.?)\s*([\d,]+\.\d{2}|[\d,]+)", re.IGNORECASE)
        amt_match = re_amount.search(text)
        utr = None
        if "UPI/" in text:
            m = re.search(r"UPI/(\d{12})", text)
            if m: utr = m.group(1)
        if not utr:
            m = re.search(r"UTR[:\s\-]+([A-Z0-9]{8,22})", text, re.IGNORECASE)
            if m: utr = m.group(1)
            
        is_trans = bool(amt_match and utr)
        return {
            "template": "ICICI_TRANSACTION",
            "is_transaction": is_trans,
            "amount": float(amt_match.group(1).replace(",", "")) if amt_match else 0.0,
            "utr": utr,
            "status": "PARSED" if is_trans else "NEEDS_REVIEW"
        }

    def _parse_sbi_credit(self, text: str) -> Dict[str, Any]:
        # Example: Your A/C XXXXX313589 has a credit by Cheque of Rs 1,87,867.00 on 21/04/26.
        re_amt = re.compile(r"Rs\s*([\d,]+\.\d{2})", re.IGNORECASE)
        re_date = re.compile(r"on\s*(\d{2}/\d{2}/\d{2,4})", re.IGNORECASE)
        
        amt_match = re_amt.search(text)
        date_match = re_date.search(text)
        
        # Mode detection
        mode = "BANK"
        if "BY CHEQUE" in text.upper(): mode = "RTGS_OR_CHEQUE"
        elif "BY TRANSFER" in text.upper(): mode = "NEFT" # Or generic transfer
        
        is_trans = bool(amt_match)
        return {
            "template": "SBI_CREDIT_ALERT",
            "is_transaction": is_trans,
            "amount": float(amt_match.group(1).replace(",", "")) if amt_match else 0.0,
            "transaction_date": date_match.group(1) if date_match else None,
            "mode": mode,
            "status": "PARSED" if is_trans else "NEEDS_REVIEW"
        }

    def _parse_generic_credit(self, text: str) -> Dict[str, Any]:
        re_amount = re.compile(r"(?:INR|Rs\.?)\s*([\d,]+\.\d{2}|[\d,]+)", re.IGNORECASE)
        amt_match = re_amount.search(text)
        return {
            "template": "GENERIC_CREDIT",
            "is_transaction": bool(amt_match),
            "amount": float(amt_match.group(1).replace(",", "")) if amt_match else 0.0,
            "status": "NEEDS_REVIEW"
        }
