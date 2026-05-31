import json
import os
import logging
from datetime import date, timedelta
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class HolidayManager:
    """Manages Bank Holidays for Maharashtra across multiple years."""
    
    BASE_DIR = "config/holidays"
    AUDIT_LOG_DIR = "C:/Aradhana/AuditLogs"
    
    def __init__(self):
        os.makedirs(self.BASE_DIR, exist_ok=True)
        os.makedirs(self.AUDIT_LOG_DIR, exist_ok=True)
        self.calendars = {} # year -> data

    def _get_filename(self, year: int) -> str:
        return os.path.join(self.BASE_DIR, f"holidays_{year}.json")

    def load_calendar(self, year: int) -> Optional[Dict]:
        """Loads the calendar for a specific year."""
        path = self._get_filename(year)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.calendars[year] = data
                return data
        return None

    def get_status(self, year: int) -> str:
        data = self.load_calendar(year)
        if not data:
            return "MISSING"
        return data.get("status", "DRAFT")

    def is_working_day(self, check_date: date) -> bool:
        """Determines if a date is a bank working day."""
        year = check_date.year
        
        # 1. Every Sunday (6)
        if check_date.weekday() == 6:
            return False
        
        # 2. Every 2nd and 4th Saturday
        if self.is_2nd_or_4th_saturday(check_date):
            return False
        
        # 3. Load Year-Specific Calendar
        data = self.calendars.get(year) or self.load_calendar(year)
        
        if not data or data.get("status") != "ACTIVE":
            # FALLSAFE: Previous known approved calendar or alert
            logger.warning(f"Active holiday calendar for {year} missing. Status: HOLIDAY_CALENDAR_REVIEW_REQUIRED")
            # For working day determination, we check if it's a fixed holiday if no active calendar exists
            # but ideally we should have an ACTIVE calendar.
            return self._is_working_day_emergency_fallback(check_date)

        date_str = check_date.strftime("%Y-%m-%d")
        return date_str not in data.get("holidays", {})

    def is_2nd_or_4th_saturday(self, check_date: date) -> bool:
        if check_date.weekday() != 5: # 5 is Saturday
            return False
        day = check_date.day
        week_num = (day - 1) // 7 + 1
        return week_num in [2, 4]

    def _is_working_day_emergency_fallback(self, check_date: date) -> bool:
        # Minimal fallback: check if it's a known fixed holiday
        fixed_holidays = {
            "01-26": "Republic Day",
            "05-01": "Maharashtra Day",
            "08-15": "Independence Day",
            "10-02": "Gandhi Jayanti",
            "12-25": "Christmas"
        }
        return check_date.strftime("%m-%d") not in fixed_holidays

    def approve_calendar(self, year: int, user: str):
        """Moves a calendar from DRAFT to ACTIVE."""
        data = self.load_calendar(year)
        if not data:
            raise ValueError(f"Calendar for {year} not found.")
        
        old_status = data.get("status")
        data["status"] = "ACTIVE"
        data["approved_by"] = user
        data["approved_at"] = date.today().isoformat()
        
        with open(self._get_filename(year), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        
        self.log_audit_event("HOLIDAY_CALENDAR_APPROVED", {
            "year": year,
            "user": user,
            "old_status": old_status,
            "new_status": "ACTIVE"
        })

    def override_holiday(self, year: int, holiday_date: str, name: str, holiday_type: str, user: str, reason: str):
        """Allows accountants to add or modify a holiday."""
        data = self.load_calendar(year)
        if not data:
            raise ValueError(f"Calendar for {year} not found.")
        
        old_value = data["holidays"].get(holiday_date)
        data["holidays"][holiday_date] = {
            "name": name,
            "type": holiday_type
        }
        
        with open(self._get_filename(year), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            
        self.log_audit_event("HOLIDAY_CALENDAR_OVERRIDE", {
            "year": year,
            "date": holiday_date,
            "old_value": old_value,
            "new_value": name,
            "user": user,
            "reason": reason
        })

    def log_audit_event(self, event_type: str, details: Dict):
        event = {
            "timestamp": date.today().isoformat(),
            "event_type": event_type,
            "details": details
        }
        filename = f"AUDIT_HOLIDAY_{event_type}_{date.today().strftime('%Y%m%d')}.json"
        path = os.path.join(self.AUDIT_LOG_DIR, filename)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
