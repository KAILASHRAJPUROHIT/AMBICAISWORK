import json
import os
import logging
from datetime import date, timedelta
from typing import Dict, List

logger = logging.getLogger(__name__)

class HolidayGenerator:
    """Generates bank holiday calendars for the upcoming year."""
    
    BASE_DIR = "config/holidays"
    
    FIXED_HOLIDAYS = [
        {"name": "Republic Day", "month": 1, "day": 26},
        {"name": "Chhatrapati Shivaji Maharaj Jayanti", "month": 2, "day": 19},
        {"name": "Dr. Babasaheb Ambedkar Jayanti", "month": 4, "day": 14},
        {"name": "Maharashtra Day", "month": 5, "day": 1},
        {"name": "Independence Day", "month": 8, "day": 15},
        {"name": "Gandhi Jayanti", "month": 10, "day": 2},
        {"name": "Christmas", "month": 12, "day": 25}
    ]

    def generate_next_year_holiday_calendar(self, year: int = None) -> str:
        """
        Generates a draft holiday calendar for the specified year.
        If year is None, generates for next year relative to today.
        """
        if year is None:
            year = date.today().year + 1
        
        logger.info(f"Generating holiday calendar draft for {year}")
        
        holidays = {}
        
        # Layer 1: Fixed Holidays
        for fh in self.FIXED_HOLIDAYS:
            d = date(year, fh["month"], fh["day"])
            holidays[d.strftime("%Y-%m-%d")] = {
                "name": fh["name"],
                "type": "FIXED"
            }
            
        # Layer 2: Calculated Saturdays (2nd and 4th)
        saturdays = self._calculate_saturdays(year)
        for d in saturdays:
            holidays[d.strftime("%Y-%m-%d")] = {
                "name": "Bank Holiday (Saturday)",
                "type": "BANK_OPERATIONAL"
            }
            
        # Layer 3: Movable Festivals (Placeholders for 2026/2027+)
        # In a real system, these would be fetched from an API or a static table.
        # For MVP, we flag that movable holidays need manual input.
        
        calendar_data = {
            "year": year,
            "status": "DRAFT",
            "generated_at": date.today().isoformat(),
            "holidays": holidays,
            "validation_warnings": [
                "Layer 3 (Movable Festivals) missing. Please update manually.",
                "Verify Holi, Diwali, Eid, and other movable dates."
            ]
        }
        
        path = os.path.join(self.BASE_DIR, f"holidays_{year}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(calendar_data, f, indent=4)
            
        self._generate_report(year, calendar_data)
        
        return path

    def _calculate_saturdays(self, year: int) -> List[date]:
        saturdays = []
        # Start from first day of year
        d = date(year, 1, 1)
        # Advance to first Saturday
        while d.weekday() != 5:
            d += timedelta(days=1)
            
        while d.year == year:
            # Check which Saturday of the month it is
            week_num = (d.day - 1) // 7 + 1
            if week_num in [2, 4]:
                saturdays.append(d)
            d += timedelta(days=7)
            
        return saturdays

    def _generate_report(self, year: int, data: Dict):
        report_path = os.path.join(self.BASE_DIR, f"holiday_generation_report_{year}.json")
        report = {
            "year": year,
            "timestamp": date.today().isoformat(),
            "fixed_count": len([h for h in data["holidays"].values() if h["type"] == "FIXED"]),
            "operational_count": len([h for h in data["holidays"].values() if h["type"] == "BANK_OPERATIONAL"]),
            "warnings": data["validation_warnings"]
        }
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4)
