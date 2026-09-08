import unittest
from datetime import date
from backend.reconciliation.holiday_manager import HolidayManager
from backend.reconciliation.holiday_generator import HolidayGenerator

class TestHolidayWorkflows(unittest.TestCase):
    def setUp(self):
        self.hm = HolidayManager()
        self.hg = HolidayGenerator()
        # Ensure clean state for test year
        self.test_year = 2030
        path = self.hm._get_filename(self.test_year)
        if os.path.exists(path):
            os.remove(path)

    def test_auto_generation(self):
        # Generate 2030 Draft
        path = self.hg.generate_next_year_holiday_calendar(self.test_year)
        self.assertTrue(os.path.exists(path))
        
        status = self.hm.get_status(self.test_year)
        self.assertEqual(status, "DRAFT")

    def test_approval_workflow(self):
        self.hg.generate_next_year_holiday_calendar(self.test_year)
        
        # Approve
        self.hm.approve_calendar(self.test_year, "Kuldeep")
        
        status = self.hm.get_status(self.test_year)
        self.assertEqual(status, "ACTIVE")
        
        # Verify specific holiday (Republic Day 2030)
        is_working = self.hm.is_working_day(date(2030, 1, 26))
        self.assertFalse(is_working)

    def test_saturday_calculation(self):
        # May 2030: 1st (Wed), 4th (Sat) -> 1st Sat
        # 11th (Sat) -> 2nd Sat (Holiday)
        # 25th (Sat) -> 4th Sat (Holiday)
        self.hg.generate_next_year_holiday_calendar(2030)
        self.hm.approve_calendar(2030, "Kuldeep")
        
        # 2nd Saturday 11-May-2030
        self.assertFalse(self.hm.is_working_day(date(2030, 5, 11)))
        # 4th Saturday 25-May-2030
        self.assertFalse(self.hm.is_working_day(date(2030, 5, 25)))
        # 3rd Saturday 18-May-2030 (Working Day)
        self.assertTrue(self.hm.is_working_day(date(2030, 5, 18)))

    def test_override_logging(self):
        self.hg.generate_next_year_holiday_calendar(self.test_year)
        self.hm.override_holiday(self.test_year, "2030-05-15", "Local Holiday", "MOVABLE", "Accountant", "Local festival")
        
        data = self.hm.load_calendar(self.test_year)
        self.assertIn("2030-05-15", data["holidays"])
        self.assertEqual(data["holidays"]["2030-05-15"]["name"], "Local Holiday")

import os
if __name__ == "__main__":
    unittest.main()
