import os
import logging
from datetime import datetime
from pywinauto import Desktop, Application
import psutil

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
LOG_DIR = os.path.join(EXPORT_BASE, "Logs")
CONTROLS_OUT = os.path.join(LOG_DIR, "payment_detail_all_windows.txt")
SCRIPT_LOG = os.path.join(LOG_DIR, "prime_payment_detail_probe.log")

# Ensure directories exist
os.makedirs(LOG_DIR, exist_ok=True)

# Setup Logging
logging.basicConfig(
    filename=SCRIPT_LOG,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    filemode="w"
)
logger = logging.getLogger(__name__)

KEYWORDS = [
    "Payment", "Detail", "ADV", "CASH", "BANK", "CARD", 
    "RTGS", "CHQ", "UPI", "NEFT", "IMPS", "Cust Purc", "BAL"
]

def find_fa_pids():
    pids = []
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] and proc.info['name'].lower() == "fa.exe":
            pids.append(proc.info['pid'])
    return pids

def probe_all_windows():
    logger.info("Starting exhaustive FA.exe window discovery")
    
    pids = find_fa_pids()
    if not pids:
        msg = "Process 'FA.exe' not found. Please ensure Prime is running."
        logger.error(msg)
        print(msg)
        return

    logger.info(f"Found FA.exe PIDs: {pids}")
    
    with open(CONTROLS_OUT, "w", encoding="utf-8") as f:
        f.write(f"Prime Exhaustive Window Discovery - {datetime.now()}\n")
        f.write("="*70 + "\n\n")

        desktop = Desktop(backend="win32")
        
        # Enumerate all top-level windows on desktop and filter by PID
        all_windows = desktop.windows()
        
        found_target = False
        for win in all_windows:
            try:
                if win.process_id() not in pids:
                    continue
                
                handle = win.handle
                title = win.window_text()
                class_name = win.class_name()
                
                f.write(f"WINDOW: '{title}'\n")
                f.write(f"  Handle: {handle} (0x{handle:X})\n")
                f.write(f"  Class:  {class_name}\n")
                f.write("-" * 40 + "\n")
                
                # Check for keywords in window title
                if any(k.lower() in title.lower() for k in KEYWORDS):
                    found_target = True

                # Enumerate all descendants
                descendants = win.descendants()
                for i, ctrl in enumerate(descendants):
                    try:
                        c_text = ctrl.window_text().strip()
                        c_class = ctrl.class_name()
                        
                        f.write(f"  [{i:03d}] {c_class:<25} | Text: '{c_text}'\n")
                        
                        if any(k.lower() in c_text.lower() for k in KEYWORDS):
                            found_target = True
                    except Exception:
                        continue
                
                f.write("\n" + "="*70 + "\n\n")
            except Exception as e:
                logger.error(f"Error processing window: {e}")
                continue

        if not found_target:
            f.write("No windows/controls matching payment keywords found.\n")
            print("Warning: No payment-related fields detected in FA.exe windows.")
        else:
            print(f"Success: Exhaustive dump saved to {CONTROLS_OUT}")
            logger.info(f"Discovery complete. Results in {CONTROLS_OUT}")

if __name__ == "__main__":
    probe_all_windows()
