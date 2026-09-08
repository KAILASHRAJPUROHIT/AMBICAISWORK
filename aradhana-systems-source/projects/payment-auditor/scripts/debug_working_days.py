import os
from datetime import date
from backend.reconciliation.holiday_manager import HolidayManager

def debug_days():
    hm = HolidayManager()
    start = date(2026, 5, 27) # Wed
    end = date(2026, 6, 1)   # Mon
    
    print(f"Checking days between {start} and {end}:")
    current = start
    while current < end:
        wd = hm.is_working_day(current)
        sat24 = hm.is_2nd_or_4th_saturday(current)
        print(f"{current} ({current.strftime('%a')}): Working={wd}, 2nd/4th Sat={sat24}")
        current += timedelta(days=1)

from datetime import timedelta
if __name__ == "__main__":
    debug_days()
