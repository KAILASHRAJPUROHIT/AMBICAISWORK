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

    def parse(self, raw_email: str) -> Dict[str, Any]:
        """
        Extracts structured fields from raw email text.
        Returns a dictionary with extracted fields.
        """
        logger.info("Parsing ICICI email sample.")
        
        data = {
            "transaction_id": None,
            "amount": 0.0,
            "mode": "UNKNOWN",
            "utr": None,
            "sender_name": None,
            "transaction_date": None,
            "raw_email": raw_email
        }
        
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
        if "UPI/" in raw_email:
            data["mode"] = "UPI"
            upi_match = self.RE_INFO_UPI.search(raw_email)
            if upi_match:
                data["utr"] = upi_match.group(1)
                data["sender_name"] = upi_match.group(2).strip()
        elif "NEFT/" in raw_email:
            data["mode"] = "NEFT"
            neft_match = self.RE_INFO_NEFT.search(raw_email)
            if neft_match:
                data["utr"] = neft_match.group(1)
                data["sender_name"] = neft_match.group(2).strip()
        elif "IMPS/" in raw_email:
            data["mode"] = "IMPS"
            imps_match = self.RE_INFO_IMPS.search(raw_email)
            if imps_match:
                data["utr"] = imps_match.group(1)
                data["sender_name"] = imps_match.group(2).strip()
        elif "RTGS/" in raw_email:
            data["mode"] = "RTGS"
            rtgs_match = self.RE_INFO_RTGS.search(raw_email)
            if rtgs_match:
                data["utr"] = rtgs_match.group(1)
                data["sender_name"] = rtgs_match.group(2).strip()
        
        # 4. Fallback for UTR if not found in specific formats
        if not data["utr"]:
            # General UTR pattern search
            utr_gen = re.search(r"(?:UTR|Ref|Reference)[:\s\-]+([A-Z0-9]{8,22})", raw_email, re.IGNORECASE)
            if utr_gen:
                data["utr"] = utr_gen.group(1)

        return data
