import logging

logger = logging.getLogger(__name__)

class StatusEngine:
    """Assigns reconciliation statuses based on defined rules."""
    
    @staticmethod
    def get_status(payment_row, match_result, validation_results):
        """
        Rules:
        - GREEN: Exact verified match.
        - YELLOW: Awaiting verification (bank modes without match).
        - ORANGE: Delivered before payment (out of scope for simple MVP, but placeholder).
        - RED: Mismatch (e.g., total mismatch).
        - BLUE: Cheque awaiting clearance.
        - GREY: Internal accounting rows (CASH, ADV, BAL) that don't match to bank.
        """
        
        # Check for RED status from total validation
        if validation_results.get("payment_status") == "RED":
            return "RED", "PAYMENT_TOTAL_MISMATCH"
            
        mode = payment_row.get("payment_mode")
        
        # BLUE status for cheques
        if mode == "RTGS_OR_CHEQUE":
             return "BLUE", "CHEQUE_AWAITING_CLEARANCE"
             
        # Bank matching rules
        bank_modes = ["UPI", "IMPS", "NEFT", "CARD"]
        if mode in bank_modes:
            if match_result:
                return "GREEN", "EXACT_VERIFIED_MATCH"
            else:
                return "YELLOW", "AWAITING_VERIFICATION"
                
        # Non-bank matching rows
        return "GREY", "ACCOUNTING_ENTRY"
