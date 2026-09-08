import os
import platform
import struct
import logging
import psutil
from pywinauto import Desktop, Application

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
LOG_OUT = os.path.join(EXPORT_BASE, "Logs", "control_access_diagnostic.txt")

os.makedirs(os.path.dirname(LOG_OUT), exist_ok=True)

def get_process_bitness(pid):
    try:
        proc = psutil.Process(pid)
        # On Windows, is_wow64() returns True if the process is 32-bit running on 64-bit Windows
        if hasattr(proc, 'is_wow64') and proc.is_wow64():
            return 32
        return 64
    except Exception:
        return "Unknown"

def run_diagnostic():
    print("Starting Control Access Diagnostic...")
    
    with open(LOG_OUT, "w", encoding="utf-8") as f:
        f.write("Prime Control Access Diagnostic\n")
        f.write("="*40 + "\n\n")

        # 1. Environment Report
        python_arch = struct.calcsize("P") * 8
        f.write(f"Python Architecture: {python_arch}-bit\n")
        
        pids = [p.info['pid'] for p in psutil.process_iter(['pid', 'name']) if p.info['name'] and p.info['name'].lower() == "fa.exe"]
        fa_bitness = "Not Running"
        if pids:
            try:
                # Alternate bitness check
                import win32process
                import win32api
                phandle = win32api.OpenProcess(0x1000, False, pids[0])
                if win32process.IsWow64Process(phandle):
                    fa_bitness = "32-bit"
                else:
                    fa_bitness = "64-bit"
            except Exception:
                fa_bitness = "32-bit (Assumed VB6)"

        f.write(f"FA.exe Architecture: {fa_bitness}\n")
        f.write(f"Bitness Mismatch: {'YES' if fa_bitness == '32-bit' and python_arch == 64 else 'NO'}\n")
        f.write(f"Pywinauto Backend: win32\n\n")

        if not pids:
            f.write("ERROR: FA.exe is not running.\n")
            return

        # 2. MDI Client Probing
        desktop = Desktop(backend="win32")
        target_form = None
        
        f.write("MDI HIERARCHY PROBE:\n")
        for win in desktop.windows():
            if win.process_id() in pids:
                if win.class_name() == "ThunderRT6MDIForm":
                    f.write(f"Found MDI Form: '{win.window_text()}'\n")
                    # MDI child forms are usually children of the MDIClient window
                    for child in win.children():
                        if child.class_name() == "MDIClient":
                            f.write(f"  Found MDIClient. Probing for sub-windows...\n")
                            for subwin in child.children():
                                f.write(f"    Sub-Window: '{subwin.window_text()}' | Class: {subwin.class_name()}\n")
                                if "Sales Bill" in subwin.window_text():
                                    target_form = subwin
                
        if not target_form:
            f.write("\nERROR: Active Sales Bill form not found within MDI hierarchy.\n")
            return

        f.write(f"Target Form: '{target_form.window_text()}'\n")
        f.write(f"Handle: {target_form.handle} (0x{target_form.handle:X})\n")
        f.write(f"Rect: {target_form.rectangle()}\n\n")

        # 3. Statistics
        all_ctrls = target_form.descendants()
        visible_ctrls = [c for c in all_ctrls if c.is_visible()]
        textboxes = [c for c in all_ctrls if c.class_name() == "ThunderRT6TextBox"]
        non_empty_tbs = [c for c in textboxes if c.window_text().strip()]

        f.write("CONTROL STATISTICS:\n")
        f.write(f"  Total Controls:      {len(all_ctrls)}\n")
        f.write(f"  Visible Controls:    {len(visible_ctrls)}\n")
        f.write(f"  TextBoxes:           {len(textboxes)}\n")
        f.write(f"  Non-Empty TextBoxes: {len(non_empty_tbs)}\n\n")

        # 4. Detailed Dump
        f.write("DETAILED CONTROL DUMP:\n")
        f.write(f"{'Handle':<10} | {'Class':<25} | {'Visible':<8} | {'Text'}\n")
        f.write("-" * 80 + "\n")
        for ctrl in all_ctrls:
            try:
                handle = f"0x{ctrl.handle:X}"
                cls = ctrl.class_name()
                vis = "YES" if ctrl.is_visible() else "NO"
                txt = ctrl.window_text().strip().replace("\n", " ").replace("\r", "")
                f.write(f"{handle:<10} | {cls:<25} | {vis:<8} | '{txt}'\n")
            except Exception:
                continue

    print(f"Diagnostic complete. Results saved to {LOG_OUT}")

if __name__ == "__main__":
    run_diagnostic()
