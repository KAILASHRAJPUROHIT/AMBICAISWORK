import os
import json
import time
import logging
import re
import subprocess
import win32gui
import win32con
from datetime import datetime, timedelta
from pywinauto import Desktop, Application
import psutil

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
JSON_OUT = os.path.join(EXPORT_BASE, "JSON", "prime_sales_report.json")
LOG_OUT = os.path.join(EXPORT_BASE, "Logs", "payment_mode_report_exporter.log")
PRIME_DIR = r"C:\Aradhana\PrimeSnapshotLatest"

os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
os.makedirs(os.path.dirname(LOG_OUT), exist_ok=True)

logging.basicConfig(filename=LOG_OUT, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def find_prime():
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] and proc.info['name'].lower() == "fa.exe":
            return proc.info['pid']
    return None

def run_export():
    logger.info("Starting Payment Mode Report Export Workflow")
    pid = find_prime()
    if not pid:
        logger.error("FA.exe not found. Ensure Prime is running.")
        return

    try:
        app = Application(backend="win32").connect(process=pid)
        mdi = app.window(class_name='ThunderRT6MDIForm')
        mdi.set_focus()
        
        # 1. Close open forms to enable menu
        for _ in range(3):
            mdi.type_keys("{ESC}")
            time.sleep(0.3)
        
        # 2. Trigger Menu Item 245 (Billwise Sale/Purc Detail (Payment Mode))
        # This was discovered to be index 20 under Miscellaneous menu
        logger.info("Triggering report menu command (ID: 245)...")
        win32gui.PostMessage(mdi.handle, win32con.WM_COMMAND, 245, 0)
        time.sleep(5) 
        
        # 3. Find the report form
        report_form = None
        for win in Desktop(backend="win32").windows():
            if win.process_id() == pid:
                txt = win.window_text().strip()
                if any(k in txt for k in ["Billwise", "Payment", "Sale/Purc"]):
                    report_form = win
                    break
        
        if not report_form:
            logger.error("Report form window not found.")
            return

        logger.info(f"Report form identified: {report_form.window_text()}")
        report_form.set_focus()
        
        # 4. Set Yesterday's Date
        yesterday = datetime.now() - timedelta(days=1)
        date_str = yesterday.strftime("%d/%m/%Y")
        logger.info(f"Setting filter date: {date_str}")
        
        tbs = report_form.descendants(class_name="ThunderRT6TextBox")
        if len(tbs) >= 2:
            # From Date
            tbs[0].set_focus()
            tbs[0].type_keys("^a{BACKSPACE}" + date_str + "{ENTER}", with_spaces=True)
            time.sleep(0.5)
            # To Date
            tbs[1].set_focus()
            tbs[1].type_keys("^a{BACKSPACE}" + date_str + "{ENTER}", with_spaces=True)
            time.sleep(1)
        
        # 5. Export to Excel
        export_btn = None
        for btn in report_form.descendants(class_name="ThunderRT6CommandButton"):
            if "Excel" in btn.window_text():
                export_btn = btn
                break
        
        if not export_btn:
            logger.error("Export button 'Excel' not found.")
            return

        logger.info("Initiating Excel Export...")
        before_files = set([f for f in os.listdir(PRIME_DIR) if f.endswith(".xls")])
        
        export_btn.click()
        time.sleep(3)
        
        # Handle Save / Overwrite dialogs
        desktop = Desktop(backend="win32")
        for win in desktop.windows():
             if win.process_id() == pid and any(k in win.window_text() for k in ["Save", "Confirm", "Exists"]):
                 logger.info(f"Accepting dialog: {win.window_text()}")
                 win.type_keys("{ENTER}")
                 time.sleep(1)

        logger.info("Waiting for export completion...")
        time.sleep(10)
        
        # 6. Locate exported file
        after_files = set([f for f in os.listdir(PRIME_DIR) if f.endswith(".xls")])
        new_files = after_files - before_files
        
        exported_path = None
        if not new_files:
            # Fallback to most recent within 60s
            all_xls = [os.path.join(PRIME_DIR, f) for f in os.listdir(PRIME_DIR) if f.endswith(".xls")]
            if all_xls:
                latest_file = max(all_xls, key=os.path.getmtime)
                if time.time() - os.path.getmtime(latest_file) < 60:
                    exported_path = latest_file
        else:
            exported_path = os.path.join(PRIME_DIR, list(new_files)[0])
        
        if exported_path:
            logger.info(f"Excel file located: {exported_path}")
            # 7. Execute 64-bit parser for data transformation
            logger.info("Executing Excel parser...")
            # We assume 'python' points to the 64-bit interpreter with pandas/xlrd
            subprocess.run(["python", "scripts/prime_excel_parser.py", exported_path])
        else:
            logger.error("Exported file not detected in Prime directory.")

    except Exception as e:
        logger.exception(f"Export workflow failed: {e}")

if __name__ == "__main__":
    run_export()
