import logging

logger = logging.getLogger(__name__)

class Matcher:
    """Matches Prime payment rows with external sources."""
    
    BANK_ORIGINATED_MODES = ["UPI", "IMPS", "NEFT", "RTGS_OR_CHEQUE", "CARD"]

    @staticmethod
    def match(payment_row, external_sources):
        """
        Attempts to find a match for a payment row.
        Only bank-originated rows participate in bank matching.
        """
        mode = payment_row.get("payment_mode")
        amount = payment_row.get("amount")
        
        if mode not in Matcher.BANK_ORIGINATED_MODES:
            logger.info(f"Skipping bank matching for non-bank mode: {mode}")
            return None

        # Logic for actual matching would go here (e.g., searching by amount, date, reference)
        # For MVP, we return None to signify it needs verification (YELLOW) 
        # unless we had explicit external data to compare against.
        
        for source in external_sources:
            if source.get("amount") == amount and source.get("mode") == mode:
                # Potential match found
                return source
        
        return None
