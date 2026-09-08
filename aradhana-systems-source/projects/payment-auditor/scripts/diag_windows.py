from pywinauto import Application
import psutil

def diag():
    print("Listing all windows for FA.exe process using Application.connect()...")
    pids = [p.info['pid'] for p in psutil.process_iter(['pid', 'name']) if p.info['name'] and p.info['name'].lower() == "fa.exe"]
    if not pids: return
    
    app = Application(backend="win32").connect(process=pids[0])
    for win in app.windows():
        print(f"WINDOW: '{win.window_text()}' | Class: {win.class_name()} | Handle: {win.handle}")
        for i, child in enumerate(win.descendants()):
             if child.window_text():
                 print(f"  [{i}] {child.class_name()} | Text: '{child.window_text()}'")

if __name__ == "__main__":
    diag()
