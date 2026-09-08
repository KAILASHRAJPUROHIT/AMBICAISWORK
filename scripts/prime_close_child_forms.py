import os
from pywinauto import Application, Desktop
import psutil
import time

def close_child_forms():
    print("Closing all MDI child forms in Prime...")
    pids = [p.info['pid'] for p in psutil.process_iter(['pid', 'name']) if p.info['name'] and p.info['name'].lower() == "fa.exe"]
    if not pids: return
    
    app = Application(backend="win32").connect(process=pids[0])
    mdi = app.window(class_name='ThunderRT6MDIForm')
    mdi.set_focus()
    
    # Try to close forms via ESC keys or finding "E&xit" buttons
    # A safer way in MDI is usually File -> Exit (which might exit the app) or just ESC
    for _ in range(5):
        mdi.type_keys("{ESC}")
        time.sleep(0.2)
    
    print("Closed children.")

if __name__ == "__main__":
    close_child_forms()
