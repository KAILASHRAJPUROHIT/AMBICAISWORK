import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class EmailNormalizer:
    """Normalizes parsed email fields to project standards."""
    
    def normalize(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cleans up and standardizes fields.
        - Standardizes payment modes.
        - Formats dates.
        - Generates internal transaction IDs.
        """
        logger.info(f"Normalizing transaction: {parsed_data.get('utr')}")
        
        normalized = parsed_data.copy()
        
        # 1. Standardize Mode
        raw_mode = str(normalized.get("mode", "UNKNOWN")).upper()
        if "UPI" in raw_mode:
            normalized["mode"] = "UPI"
        elif "NEFT" in raw_mode:
            normalized["mode"] = "NEFT"
        elif "IMPS" in raw_mode:
            normalized["mode"] = "IMPS"
        elif "RTGS" in raw_mode:
            normalized["mode"] = "RTGS"
        else:
            normalized["mode"] = "UNKNOWN"
            
        # 2. Standardize Date
        raw_date = normalized.get("transaction_date")
        if raw_date:
            # Common formats: 31-May-26, 31-May-2026, 31/05/2026, 31-05-2026
            found_date = False
            for fmt in ["%d-%b-%y", "%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d/%m/%y"]:
                try:
                    dt = datetime.strptime(raw_date, fmt)
                    normalized["transaction_date"] = dt.strftime("%Y-%m-%d")
                    found_date = True
                    break
                except ValueError:
                    continue
            
            if not found_date:
                 logger.warning(f"Could not normalize date: {raw_date}")
                
        # 3. Generate internal ID (BANK_UTR_DATE)
        utr = normalized.get("utr", "NOUTR")
        date_str = normalized.get("transaction_date", "NODATE")
        normalized["transaction_id"] = f"ICICI_{utr}_{date_str}"
        
        return normalized
