import logging

logger = logging.getLogger(__name__)

class PaymentClassifier:
    """Classifies payment modes into standardized types."""
    
    SUPPORTED_MODES = [
        "ADVANCE", "BALANCE", "CASH", "CARD", "UPI", 
        "IMPS", "NEFT", "RTGS_OR_CHEQUE", "OLD_GOLD_EXCHANGE", "UNKNOWN"
    ]

    @staticmethod
    def classify(raw_mode: str) -> str:
        if not raw_mode:
            return "UNKNOWN"
        
        mode = raw_mode.upper().strip()
        
        if "CASH" in mode:
            return "CASH"
        if "UPI" in mode or "G-PAY" in mode or "GPAY" in mode or "PHONEPE" in mode:
            return "UPI"
        if "CARD" in mode or "POS" in mode:
            return "CARD"
        if "ADV" in mode:
            return "ADVANCE"
        if "BAL" in mode:
            return "BALANCE"
        if "NEFT" in mode:
            return "NEFT"
        if "IMPS" in mode:
            return "IMPS"
        if "RTGS" in mode or "CHQ" in mode or "CHEQUE" in mode:
            return "RTGS_OR_CHEQUE"
        if "OLD" in mode and "GOLD" in mode:
            return "OLD_GOLD_EXCHANGE"
            
        return "UNKNOWN"
