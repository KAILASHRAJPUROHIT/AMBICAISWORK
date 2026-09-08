from datetime import date, timedelta
from .holiday_manager import HolidayManager

class WorkingDayCalendar:
    """Calculates bank working days in Maharashtra."""
    
    def __init__(self):
        self.holiday_manager = HolidayManager()

    def add_working_days(self, start_date: date, days: int) -> date:
        """Adds a specific number of working days to a date."""
        current_date = start_date
        added_days = 0
        
        while added_days < days:
            current_date += timedelta(days=1)
            if self.holiday_manager.is_working_day(current_date):
                added_days += 1
        
        return current_date

    def get_elapsed_working_days(self, start_date: date, end_date: date) -> int:
        """Calculates working days between two dates (inclusive of end, exclusive of start)."""
        if start_date >= end_date:
            return 0
            
        elapsed = 0
        current_date = start_date + timedelta(days=1)
        while current_date <= end_date:
            if self.holiday_manager.is_working_day(current_date):
                elapsed += 1
            current_date += timedelta(days=1)
            
        return elapsed
