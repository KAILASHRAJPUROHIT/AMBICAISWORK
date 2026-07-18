import unittest
from datetime import date
from backend.reconciliation.holiday_manager import HolidayManager
from backend.reconciliation.working_day_calendar import WorkingDayCalendar
from backend.reconciliation.payment_sla import PaymentSLAEngine
from backend.reconciliation.status_engine_v2 import StatusEngineV2

class TestPaymentSLA(unittest.TestCase):
    def setUp(self):
        self.holiday_manager = HolidayManager()
        self.calendar = WorkingDayCalendar()
        self.sla_engine = PaymentSLAEngine()
        self.status_engine = StatusEngineV2()

    def test_sunday_exclusion(self):
        # 2026-05-31 is Sunday
        self.assertFalse(self.holiday_manager.is_working_day(date(2026, 5, 31)))

    def test_2nd_saturday_exclusion(self):
        # May 2026: 1st (Fri), 2nd (Sat) -> 1st Sat
        # 9th (Sat) -> 2nd Sat
        self.assertFalse(self.holiday_manager.is_working_day(date(2026, 5, 9)))

    def test_4th_saturday_exclusion(self):
        # May 2026: 23rd -> 4th Sat
        self.assertFalse(self.holiday_manager.is_working_day(date(2026, 5, 23)))

    def test_maharashtra_holiday_exclusion(self):
        # 2026-05-01 is Maharashtra Day
        self.assertFalse(self.holiday_manager.is_working_day(date(2026, 5, 1)))

    def test_upi_same_day_sla(self):
        # UPI should be confirmed same day (0 working days allowed)
        inv_date = date(2026, 5, 27) # Wed
        aging = self.sla_engine.calculate_aging(inv_date, date(2026, 5, 27), "UPI")
        self.assertEqual(aging["status_color"], "GREEN")
        
        # If it's next day, it's RED (Overdue)
        aging_next = self.sla_engine.calculate_aging(inv_date, date(2026, 5, 28), "UPI")
        self.assertEqual(aging_next["status_color"], "RED")

    def test_neft_next_day_sla(self):
        # NEFT allows 1 working day
        inv_date = date(2026, 5, 27) # Wed
        # Same day is 0% elapsed (GREEN)
        aging_same = self.sla_engine.calculate_aging(inv_date, date(2026, 5, 27), "NEFT")
        self.assertEqual(aging_same["status_color"], "GREEN")
        self.assertEqual(aging_same["elapsed_percentage"], 0.0)
        
        # Next working day (Thu) is 100% elapsed (RED) - wait, rule says 0-49 GREEN, 100+ RED
        # If it's the exact allowed day, it hits the deadline. 
        aging_next = self.sla_engine.calculate_aging(inv_date, date(2026, 5, 28), "NEFT")
        self.assertEqual(aging_next["status_color"], "RED")
        self.assertEqual(aging_next["elapsed_percentage"], 100.0)

    def test_cheque_4_day_rule(self):
        # Cheque allows 4 working days
        inv_date = date(2026, 5, 27) # Wed
        # Wed (X), Thu (1), Fri (2), Sat (3), Sun (X), Mon (4)
        # Mon (working day 4) should be RED (100%)
        aging_mon = self.sla_engine.calculate_aging(inv_date, date(2026, 6, 1), "CHEQUE")
        self.assertEqual(aging_mon["elapsed_working_days"], 4)
        self.assertEqual(aging_mon["status_color"], "RED")
        
        # Thursday (working day 1) should be GREEN (25%)
        aging_thu = self.sla_engine.calculate_aging(inv_date, date(2026, 5, 28), "CHEQUE")
        self.assertEqual(aging_thu["elapsed_working_days"], 1)
        self.assertEqual(aging_thu["status_color"], "GREEN")
        
        # Friday (working day 2) should be YELLOW (50%)
        aging_fri = self.sla_engine.calculate_aging(inv_date, date(2026, 5, 29), "CHEQUE")
        self.assertEqual(aging_fri["elapsed_working_days"], 2)
        self.assertEqual(aging_fri["status_color"], "YELLOW")

    def test_cash_auto_confirm(self):
        res = self.status_engine.determine_status("2026-05-27", {"payment_mode": "CASH", "amount": 1000})
        self.assertEqual(res["payment_status"], "CASH_CONFIRMED")
        self.assertTrue(res["is_received"])

    def test_bank_match_auto_confirm(self):
        payment = {"payment_mode": "UPI", "amount": 5000}
        evidence = {"utr": "REF123", "amount": 5000, "transaction_date": "2026-05-27"}
        res = self.status_engine.determine_status("2026-05-27", payment, bank_evidence=evidence)
        self.assertEqual(res["payment_status"], "BANK_CONFIRMED")
        self.assertEqual(res["bank_reference"], "REF123")

if __name__ == "__main__":
    unittest.main()
