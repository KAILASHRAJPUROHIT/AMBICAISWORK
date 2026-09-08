import os
import logging
import json
from datetime import datetime
from pywinauto import Desktop
import psutil

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
LOG_DIR = os.path.join(EXPORT_BASE, "Logs")
DIFF_OUT = os.path.join(LOG_DIR, "payment_detail_before_after_diff.txt")
SCRIPT_LOG = os.path.join(LOG_DIR, "prime_payment_detail_diff.log")

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
    "ADV", "BAL", "CASH", "BANK", "CARD", "RTGS", "CHQ", 
    "UPI", "NEFT", "IMPS", "Cust Purc", "Payment", "Detail"
]

def find_fa_pids():
    pids = []
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] and proc.info['name'].lower() == "fa.exe":
            pids.append(proc.info['pid'])
    return pids

def capture_snapshot(pids):
    snapshot = {}
    desktop = Desktop(backend="win32")
    windows = desktop.windows()
    
    for win in windows:
        try:
            if win.process_id() not in pids:
                continue
            
            w_handle = win.handle
            w_info = {
                "handle": w_handle,
                "title": win.window_text(),
                "class": win.class_name(),
                "rect": str(win.rectangle()),
                "controls": []
            }
            
            descendants = win.descendants()
            for ctrl in descendants:
                try:
                    w_info["controls"].append({
                        "handle": ctrl.handle,
                        "class": ctrl.class_name(),
                        "text": ctrl.window_text().strip(),
                        "rect": str(ctrl.rectangle())
                    })
                except Exception:
                    continue
            
            snapshot[w_handle] = w_info
        except Exception as e:
            logger.error(f"Error capturing window {win.handle}: {e}")
            continue
            
    return snapshot

def write_diff(before, after):
    with open(DIFF_OUT, "w", encoding="utf-8") as f:
        f.write(f"Prime Payment Detail Diff Probe - {datetime.now()}\n")
        f.write("="*70 + "\n\n")

        # 1. New Windows
        new_window_handles = set(after.keys()) - set(before.keys())
        f.write(f"NEW WINDOWS DETECTED: {len(new_window_handles)}\n")
        for h in new_window_handles:
            win = after[h]
            f.write(f"  Title: '{win['title']}' | Class: {win['class']} | Handle: {h}\n")
            for i, ctrl in enumerate(win['controls']):
                f.write(f"    [{i:03d}] {ctrl['class']:<25} | Text: '{ctrl['text']}'\n")
        f.write("\n" + "-"*40 + "\n\n")

        # 2. Changed Windows (New or Changed Controls)
        f.write("CONTROLS ANALYSIS (Existing Windows):\n")
        for h in set(before.keys()) & set(after.keys()):
            win_before = before[h]
            win_after = after[h]
            
            before_ctrls = {c['handle']: c for c in win_before['controls']}
            after_ctrls = {c['handle']: c for c in win_after['controls']}
            
            new_ctrl_handles = set(after_ctrls.keys()) - set(before_ctrls.keys())
            
            if new_ctrl_handles or win_before['title'] != win_after['title']:
                f.write(f"WINDOW UPDATED: '{win_after['title']}' (Handle: {h})\n")
                
                if new_ctrl_handles:
                    f.write(f"  NEW CONTROLS ({len(new_ctrl_handles)}):\n")
                    for nh in new_ctrl_handles:
                        c = after_ctrls[nh]
                        f.write(f"    Class: {c['class']:<25} | Text: '{c['text']}'\n")
                
                # Check for changed text in existing controls
                changed_text = []
                for ch in set(before_ctrls.keys()) & set(after_ctrls.keys()):
                    if before_ctrls[ch]['text'] != after_ctrls[ch]['text']:
                        changed_text.append(after_ctrls[ch])
                
                if changed_text:
                    f.write(f"  TEXT CHANGED ({len(changed_text)}):\n")
                    for c in changed_text:
                        old_text = before_ctrls[c['handle']]['text']
                        f.write(f"    Class: {c['class']:<25} | '{old_text}' -> '{c['text']}'\n")
                
                f.write("\n")

        # 3. Keyword Match in 'After' Snapshot
        f.write("PAYMENT KEYWORD MATCHES (AFTER SNAPSHOT):\n")
        for h, win in after.items():
            if any(k.lower() in win['title'].lower() for k in KEYWORDS):
                f.write(f"  WINDOW MATCH: '{win['title']}'\n")
            
            for ctrl in win['controls']:
                if any(k.lower() in ctrl['text'].lower() for k in KEYWORDS):
                    f.write(f"  CONTROL MATCH in '{win['title']}': [{ctrl['class']}] Text: '{ctrl['text']}'\n")

def main():
    print("Starting Prime Payment Detail Diff Probe...")
    pids = find_fa_pids()
    if not pids:
        print("Error: Process 'FA.exe' not found.")
        return

    print("Step 1: Capturing 'BEFORE' state (Invoice open)...")
    before_state = capture_snapshot(pids)
    print(f"Captured {len(before_state)} windows.")

    input("\nACTION REQUIRED:\n1. Manually click 'Payment Detail' in Prime.\n2. Ensure the detail window is visible.\n3. Press Enter here to capture 'AFTER' state...")

    print("\nStep 2: Capturing 'AFTER' state...")
    after_state = capture_snapshot(pids)
    print(f"Captured {len(after_state)} windows.")

    print(f"Step 3: Calculating differences and writing to {DIFF_OUT}...")
    write_diff(before_state, after_state)
    print("Success: Diff probe complete.")

if __name__ == "__main__":
    main()
