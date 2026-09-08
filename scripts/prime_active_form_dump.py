import os
import logging
from pywinauto import Desktop
import psutil

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
LOG_OUT = os.path.join(EXPORT_BASE, "Logs", "active_form_dump.txt")

os.makedirs(os.path.dirname(LOG_OUT), exist_ok=True)

def dump_active_forms():
    print("Starting active form dump...")
    try:
        pids = [p.info['pid'] for p in psutil.process_iter(['pid', 'name']) if p.info['name'] and p.info['name'].lower() == "fa.exe"]
        if not pids:
            print("FA.exe not found.")
            return

        desktop = Desktop(backend="win32")
        
        with open(LOG_OUT, "w", encoding="utf-8") as f:
            f.write(f"Active Form Dump - {os.popen('date /t').read().strip()} {os.popen('time /t').read().strip()}\n")
            f.write("="*80 + "\n\n")

            for win in desktop.windows():
                try:
                    if win.process_id() not in pids:
                        continue
                    
                    title = win.window_text()
                    handle = win.handle
                    rect = win.rectangle()
                    is_visible = win.is_visible()
                    is_enabled = win.is_enabled()
                    
                    f.write(f"TOP-LEVEL WINDOW: '{title}'\n")
                    f.write(f"  Handle: {handle} | Class: {win.class_name()}\n")
                    f.write(f"  Rect:   {rect} | Visible: {is_visible} | Enabled: {is_enabled}\n")
                    f.write("-" * 40 + "\n")

                    # Enumerate ThunderRT6FormDC descendants
                    forms = win.descendants(class_name="ThunderRT6FormDC")
                    for i, form in enumerate(forms):
                        f_title = form.window_text().strip()
                        f_handle = form.handle
                        f_rect = form.rectangle()
                        f_visible = form.is_visible()
                        
                        f.write(f"  FORM [{i}]: '{f_title}'\n")
                        f.write(f"    Handle: {f_handle} | Rect: {f_rect} | Visible: {f_visible}\n")
                        
                        tbs = form.descendants(class_name="ThunderRT6TextBox")
                        f.write(f"    TextBox Count: {len(tbs)}\n")
                        
                        non_empty = []
                        for tb in tbs:
                            val = tb.window_text().strip()
                            if val:
                                non_empty.append(val)
                        
                        if non_empty:
                            f.write("    Non-Empty Values:\n")
                            for val in non_empty:
                                f.write(f"      - '{val}'\n")
                        f.write("\n")
                    
                    f.write("="*80 + "\n\n")

                except Exception as e:
                    f.write(f"Error probing window: {e}\n")
                    continue
        
        print(f"Dump complete. Results saved to {LOG_OUT}")

    except Exception as e:
        print(f"Critical error during dump: {e}")

if __name__ == "__main__":
    dump_active_forms()
