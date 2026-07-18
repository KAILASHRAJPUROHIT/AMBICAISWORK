import os
import json
import time
import logging
from datetime import datetime, timedelta
from pywinauto import Desktop, Application
import psutil

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
JSON_OUT = os.path.join(EXPORT_BASE, "JSON", "prime_sales_report.json")
LOG_OUT = os.path.join(EXPORT_BASE, "Logs", "payment_mode_report_exporter.log")

os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
os.makedirs(os.path.dirname(LOG_OUT), exist_ok=True)

logging.basicConfig(filename=LOG_OUT, level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def find_prime():
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] and proc.info['name'].lower() == "fa.exe":
            return proc.info['pid']
    return None

def run_export():
    logger.info("Starting Payment Mode Report Export")
    pid = find_prime()
    if not pid:
        logger.error("FA.exe not found.")
        return

    try:
        app = Application(backend="win32").connect(process=pid)
        mdi = app.window(class_name='ThunderRT6MDIForm')
        mdi.set_focus()
        
        # 1. Open report
        logger.info("Opening report menu...")
        mdi.menu_select("Miscellaneous -> Billwise Sale/Purc Detail (Payment Mode)")
        time.sleep(2) # Wait for form
        
        # 2. Find the report form
        report_form = None
        for child in mdi.descendants(class_name="ThunderRT6FormDC"):
            if "Payment Mode" in child.window_text():
                report_form = child
                break
        
        if not report_form:
            logger.error("Report form not found after menu selection.")
            return

        logger.info(f"Targeting report form: {report_form.window_text()}")
        
        # 3. Set Yesterday's Date
        yesterday = datetime.now() - timedelta(days=1)
        date_str = yesterday.strftime("%d/%m/%Y")
        logger.info(f"Setting date to: {date_str}")
        
        # Find date textboxes - usually there are two (From, To)
        tbs = report_form.descendants(class_name="ThunderRT6TextBox")
        if len(tbs) >= 2:
            # Type into From and To
            tbs[0].set_focus()
            tbs[0].type_keys("^a{BACKSPACE}" + date_str + "{ENTER}", with_spaces=True)
            time.sleep(0.5)
            tbs[1].set_focus()
            tbs[1].type_keys("^a{BACKSPACE}" + date_str + "{ENTER}", with_spaces=True)
            time.sleep(0.5)
        
        # 4. Click Export Excel
        export_btn = None
        for btn in report_form.descendants(class_name="ThunderRT6CommandButton"):
            if "Excel" in btn.window_text():
                export_btn = btn
                break
        
        if not export_btn:
            logger.error("Export button not found.")
            return

        logger.info("Clicking Export to Excel...")
        export_btn.click()
        time.sleep(5) # Wait for excel to generate
        
        # NOTE: Prime usually saves to a default path like C:\Aradhana\Prime\Exports or opens Excel directly.
        # We need to find the latest .xls/.xlsx file in the expected export directory.
        # Or handle the Save As dialog if it appears.
        
    except Exception as e:
        logger.exception(f"Export failed: {e}")

if __name__ == "__main__":
    run_export()
