import os
from pywinauto import Desktop
import psutil
import time

def force_visibility():
    print("Enforcing Prime visibility...")
    try:
        pids = [p.info['pid'] for p in psutil.process_iter(['pid', 'name']) if p.info['name'] and p.info['name'].lower() == "fa.exe"]
        if not pids:
            print("FA.exe not found.")
            return

        desktop = Desktop(backend="win32")
        
        for win in desktop.windows():
            if win.process_id() in pids:
                title = win.window_text()
                # Focus main window
                if "SHREE ARADHANA" in title or "FA" == title:
                    print(f"Restoring/Maximizing main window: {title}")
                    if win.is_minimized():
                        win.restore()
                    win.maximize()
                    win.set_focus()
                    time.sleep(0.5)

                # Focus child forms
                for form in win.descendants(class_name="ThunderRT6FormDC"):
                    f_title = form.window_text()
                    if "Sales" in f_title or "Bill" in f_title or "Payment" in f_title:
                        print(f"Ensuring form visibility: {f_title}")
                        if form.is_minimized():
                            form.restore()
                        form.set_focus()
                        time.sleep(0.2)

        print("Visibility enforcement complete.")

    except Exception as e:
        print(f"Error during visibility enforcement: {e}")

if __name__ == "__main__":
    force_visibility()
