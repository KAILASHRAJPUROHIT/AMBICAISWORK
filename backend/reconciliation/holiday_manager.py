import json
import os
from datetime import date, timedelta
from typing import List, Dict

class HolidayManager:
    """Manages Bank Holidays for Maharashtra."""
    
    HOLIDAY_FILE = "backend/reconciliation/holidays.json"
    
    def __init__(self):
        self.holidays_cache = {}
        self._ensure_holiday_file()
        self._load_holidays()

    def _ensure_holiday_file(self):
        """Creates a default holiday file for 2026 if missing."""
        if not os.path.exists(self.HOLIDAY_FILE):
            default_2026 = {
                "2026": {
                    "2026-01-26": "Republic Day",
                    "2026-02-19": "Chhatrapati Shivaji Maharaj Jayanti",
                    "2026-03-04": "Holi",
                    "2026-03-19": "Gudhi Padwa",
                    "2026-03-20": "Ramzan Id",
                    "2026-03-28": "Ram Navami",
                    "2026-03-31": "Mahavir Jayanti",
                    "2026-04-01": "Annual Bank Account Closing",
                    "2026-04-03": "Good Friday",
                    "2026-04-14": "Dr. Babasaheb Ambedkar Jayanti",
                    "2026-05-01": "Maharashtra Day",
                    "2026-05-02": "Buddha Purnima",
                    "2026-06-16": "Bakri Eid",
                    "2026-07-25": "Muharram",
                    "2026-08-15": "Independence Day",
                    "2026-08-17": "Parsi New Year",
                    "2026-08-26": "Eid-e-Milad",
                    "2026-09-14": "Ganesh Chaturthi",
                    "2026-10-02": "Gandhi Jayanti",
                    "2026-10-21": "Dasara",
                    "2026-11-09": "Diwali (Bali Pratipada)",
                    "2026-11-24": "Guru Nanak Jayanti",
                    "2026-12-25": "Christmas"
                }
            }
            with open(self.HOLIDAY_FILE, "w", encoding="utf-8") as f:
                json.dump(default_2026, f, indent=4)

    def _load_holidays(self):
        if os.path.exists(self.HOLIDAY_FILE):
            with open(self.HOLIDAY_FILE, "r", encoding="utf-8") as f:
                self.holidays_cache = json.load(f)

    def get_bank_holidays(self, year: int) -> Dict[str, str]:
        return self.holidays_cache.get(str(year), {})

    def is_bank_holiday(self, check_date: date) -> bool:
        year_str = str(check_date.year)
        date_str = check_date.strftime("%Y-%m-%d")
        return date_str in self.holidays_cache.get(year_str, {})

    def is_2nd_or_4th_saturday(self, check_date: date) -> bool:
        if check_date.weekday() != 5: # 5 is Saturday
            return False
        
        # Calculate which Saturday of the month it is
        day = check_date.day
        # 1-7: 1st, 8-14: 2nd, 15-21: 3rd, 22-28: 4th, 29-31: 5th
        week_num = (day - 1) // 7 + 1
        return week_num in [2, 4]

    def is_working_day(self, check_date: date) -> bool:
        # 1. Every Sunday (6)
        if check_date.weekday() == 6:
            return False
        
        # 2. Every 2nd and 4th Saturday
        if self.is_2nd_or_4th_saturday(check_date):
            return False
        
        # 3. Maharashtra Bank Holidays
        if self.is_bank_holiday(check_date):
            return False
            
        return True
