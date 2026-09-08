from datetime import date
from typing import Dict, Any
from .working_day_calendar import WorkingDayCalendar

class PaymentSLAEngine:
    """Calculates Payment Confirmation SLA and Aging."""
    
    # SLA Config: Allowed working days by mode
    SLA_CONFIG = {
        "CASH": 0,
        "UPI": 0,
        "IMPS": 0,
        "NEFT": 1,
        "RTGS": 1,
        "CARD": 1,
        "CHEQUE": 4
    }

    def __init__(self):
        self.calendar = WorkingDayCalendar()

    def get_expected_date(self, invoice_date: date, mode: str) -> date:
        allowed_days = self.SLA_CONFIG.get(mode, 1)
        return self.calendar.add_working_days(invoice_date, allowed_days)

    def calculate_aging(self, invoice_date: date, current_date: date, mode: str) -> Dict[str, Any]:
        allowed_days = self.SLA_CONFIG.get(mode, 1)
        elapsed_days = self.calendar.get_elapsed_working_days(invoice_date, current_date)
        
        # Color Status Rules
        # If allowed is 0 (Instant):
        #   elapsed 0 -> GREEN
        #   elapsed >= 1 -> RED
        # If allowed > 0:
        #   elapsed/allowed %
        
        status_color = "GREEN"
        elapsed_percentage = 0.0

        if allowed_days == 0:
            if elapsed_days > 0:
                status_color = "RED"
                elapsed_percentage = 100.0
        else:
            elapsed_percentage = (elapsed_days / allowed_days) * 100
            if elapsed_percentage >= 100.0:
                status_color = "RED"
            elif elapsed_percentage >= 50.0:
                status_color = "YELLOW"
            
        return {
            "expected_confirmation_date": self.get_expected_date(invoice_date, mode).strftime("%Y-%m-%d"),
            "allowed_working_days": allowed_days,
            "elapsed_working_days": elapsed_days,
            "elapsed_percentage": round(elapsed_percentage, 2),
            "status_color": status_color
        }
