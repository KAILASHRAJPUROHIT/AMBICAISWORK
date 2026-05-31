import logging
from datetime import date
from typing import Dict, Any, Optional
from .payment_sla import PaymentSLAEngine

logger = logging.getLogger(__name__)

class StatusEngineV2:
    """Enhanced Status Engine with SLA and Bank Confirmation logic."""
    
    def __init__(self):
        self.sla_engine = PaymentSLAEngine()

    def determine_status(self, 
                        invoice_date_str: str, 
                        payment_row: Dict[str, Any], 
                        bank_evidence: Optional[Dict[str, Any]] = None,
                        current_date: date = None) -> Dict[str, Any]:
        """
        Assigns reconciliation status based on bank matching and SLA aging.
        """
        if current_date is None:
            current_date = date.today()
            
        inv_date = date.fromisoformat(invoice_date_str)
        mode = payment_row.get("payment_mode", "UNKNOWN")
        amount = payment_row.get("amount", 0.0)
        
        # 1. Immediate Cash Confirmation
        if mode == "CASH":
            return {
                "payment_status": "CASH_CONFIRMED",
                "status_color": "GREEN",
                "reason": "IMMEDIATE_CASH_RECEIPT",
                "is_received": True
            }

        # 2. Bank Evidence Matching (Auto-Confirm)
        if bank_evidence:
            # SAFETY CHECK: Exact amount match
            if abs(bank_evidence.get("amount", 0.0) - amount) < 0.01:
                return {
                    "payment_status": "BANK_CONFIRMED",
                    "status_color": "GREEN",
                    "reason": "EXACT_BANK_MATCH",
                    "bank_reference": bank_evidence.get("utr"),
                    "confirmation_date": bank_evidence.get("transaction_date"),
                    "is_received": True
                }
            else:
                return {
                    "payment_status": "RED",
                    "status_color": "RED",
                    "reason": "BANK_AMOUNT_MISMATCH",
                    "is_received": False
                }

        # 3. Pending Payment Aging (SLA)
        aging = self.sla_engine.calculate_aging(inv_date, current_date, mode)
        
        # Special check for overdue cheques
        status = "PENDING"
        reason = "AWAITING_BANK_CONFIRMATION"
        
        if mode == "CHEQUE" and aging["status_color"] == "RED":
            status = "CHEQUE_PENDING_OVERDUE"
            reason = "SLA_EXCEEDED"
        elif aging["status_color"] == "RED":
            status = "RED"
            reason = "SLA_EXCEEDED"

        return {
            "payment_status": status,
            "status_color": aging["status_color"],
            "reason": reason,
            "aging": aging,
            "is_received": False
        }
