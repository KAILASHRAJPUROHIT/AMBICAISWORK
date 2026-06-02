import re
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class EmailParser:
    """Parses ICICI Bank transaction emails."""
    
    # Patterns for ICICI Bank Alerts
    # Credit Alert: Your A/c XX123 is credited with INR 5,000.00 on 31-May-26. Info: INF/NEFT/123456789/SENDER NAME.
    # UPI Alert: Your A/c XX123 is credited with INR 1,200.00 on 31-May-26. Info: UPI/612345678901/PAYEE NAME/BANK/REF.
    
    RE_AMOUNT = re.compile(r"(?:INR|Rs\.?)\s*([\d,]+\.\d{2}|[\d,]+)", re.IGNORECASE)
    RE_DATE = re.compile(r"(\d{1,2}[-/\s][A-Za-z]{3,9}[-/\s]\d{2,4}|\d{1,2}[-/\s]\d{1,2}[-/\s]\d{2,4})")
    
    # ICICI specific Info string parsing
    # Format 1: UPI/UTR/SENDER/BANK/...
    # Format 2: INF/NEFT/UTR/SENDER...
    RE_INFO_UPI = re.compile(r"UPI/(\d{12})/([^/]+)", re.IGNORECASE)
    RE_INFO_NEFT = re.compile(r"INF/NEFT/([A-Z0-9]+)/([^/]+)", re.IGNORECASE)
    RE_INFO_IMPS = re.compile(r"INF/IMPS/([0-9]+)/([^/]+)", re.IGNORECASE)
    RE_INFO_RTGS = re.compile(r"INF/RTGS/([A-Z0-9]+)/([^/]+)", re.IGNORECASE)

    def interpret_event(self, text: str) -> Dict[str, str]:
        """Interprets bank alert text into auditor-friendly meaning."""
        text = text.upper()
        
        # Default
        event_type = "GENERAL_ALERT"
        explanation = "Received bank alert - needs review."
        
        if "UPI RECEIVED" in text or "UPI" in text and "CREDITED" in text:
            event_type = "UPI_RECEIVED"
            explanation = "Customer payment received via UPI."
        elif "NEFT RECEIVED" in text or "NEFT" in text and "CREDITED" in text:
            event_type = "NEFT_RECEIVED"
            explanation = "Customer payment received via NEFT."
        elif "IMPS RECEIVED" in text or "IMPS" in text and "CREDITED" in text:
            event_type = "IMPS_RECEIVED"
            explanation = "Customer payment received via IMPS."
        elif "RTGS RECEIVED" in text or "RTGS" in text and "CREDITED" in text:
            event_type = "RTGS_RECEIVED"
            explanation = "Customer payment received via RTGS."
        elif "CREDITED" in text or "CREDIT RECEIVED" in text:
            event_type = "CREDIT_RECEIVED"
            explanation = "Funds received in account."
            
        elif "CHEQUE CLEARED" in text or "CHQ CLEARED" in text:
            event_type = "CHEQUE_CLEARED"
            explanation = "Cheque funds received and cleared."
        elif "CHEQUE DEPOSITED" in text or "SENT FOR CLEARING" in text:
            event_type = "CHEQUE_DEPOSITED"
            explanation = "Cheque deposited - waiting for clearing."
        elif "CHEQUE RETURNED" in text or "BOUNCED" in text or "RETURNED" in text and "CHQ" in text:
            event_type = "CHEQUE_RETURNED"
            explanation = "CRITICAL: Cheque failed/bounced. Immediate action required."
            
        elif "DEBIT" in text or "REVERSAL" in text:
            event_type = "DEBIT_OR_REVERSAL"
            explanation = "Possible reversal or outgoing transaction - check for fraud or errors."

        return {"event_type": event_type, "explanation": explanation}

    def parse(self, raw_email: str) -> Dict[str, Any]:
        """
        Extracts structured fields from raw email text.
        Returns a dictionary with extracted fields.
        """
        logger.info("Parsing bank email alert.")
        
        data = {
            "transaction_id": None,
            "amount": 0.0,
            "mode": "UNKNOWN",
            "utr": None,
            "sender_name": None,
            "transaction_date": None,
            "raw_email": raw_email,
            "event_type": "GENERAL",
            "auditor_explanation": ""
        }
        
        # Interpret event
        event_info = self.interpret_event(raw_email)
        data["event_type"] = event_info["event_type"]
        data["auditor_explanation"] = event_info["explanation"]
        
        # 1. Extract Amount
        amt_match = self.RE_AMOUNT.search(raw_email)
        if amt_match:
            try:
                data["amount"] = float(amt_match.group(1).replace(",", ""))
            except ValueError:
                pass
        
        # 2. Extract Date
        date_match = self.RE_DATE.search(raw_email)
        if date_match:
            data["transaction_date"] = date_match.group(1)
            
        # 3. Extract Mode, UTR, and Sender from Info string
        if "UPI/" in raw_email.upper():
            data["mode"] = "UPI"
            upi_match = self.RE_INFO_UPI.search(raw_email)
            if upi_match:
                data["utr"] = upi_match.group(1)
                data["sender_name"] = upi_match.group(2).strip()
        elif "NEFT/" in raw_email.upper():
            data["mode"] = "NEFT"
            neft_match = self.RE_INFO_NEFT.search(raw_email)
            if neft_match:
                data["utr"] = neft_match.group(1)
                data["sender_name"] = neft_match.group(2).strip()
        elif "IMPS/" in raw_email.upper():
            data["mode"] = "IMPS"
            imps_match = self.RE_INFO_IMPS.search(raw_email)
            if imps_match:
                data["utr"] = imps_match.group(1)
                data["sender_name"] = imps_match.group(2).strip()
        elif "RTGS/" in raw_email.upper():
            data["mode"] = "RTGS"
            rtgs_match = self.RE_INFO_RTGS.search(raw_email)
            if rtgs_match:
                data["utr"] = rtgs_match.group(1)
                data["sender_name"] = rtgs_match.group(2).strip()
        
        # 4. Fallback for UTR if not found in specific formats
        if not data["utr"]:
            utr_gen = re.search(r"(?:UTR|Ref|Reference|CHQ|CHEQUE)[:\s\-]+([A-Z0-9]{6,22})", raw_email, re.IGNORECASE)
            if utr_gen:
                data["utr"] = utr_gen.group(1)

        return data
