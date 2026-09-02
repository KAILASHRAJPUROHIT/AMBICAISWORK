"""Always-on-top Windows transaction notifications without a browser.

Run this on any trusted LAN PC. Set BANK_ACTIVITY_URL to the Billing-PC API
URL when the notifier is not running on the Billing PC itself.
"""
import json
import os
import tkinter as tk
import ctypes
from datetime import datetime, timezone
from urllib.request import urlopen

SETTINGS_PATH = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "AradhanaBankActivityNotifier", "settings.json")
LOG_PATH = os.path.join(os.path.dirname(SETTINGS_PATH), "runtime.log")
LOGO_PATH = r"C:\Content\Logos\Logo Dimensions in Reel 30% x=220 y=200.png"
if not os.path.exists(LOGO_PATH):
    LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
NAVY, GOLD, LIGHT_GOLD, INK = "#23519D", "#CCA137", "#F7CA5B", "#10254A"
DEFAULTS = {"server_url": "http://ARADHANA:8000/api/bank-activity", "poll_seconds": 1, "display_seconds": 30, "opacity": 92, "max_alerts": 3, "sound": False, "sound_threshold": 100000, "position": "centre-right", "enabled": True, "paused_until": None, "popup_width": 360, "popup_height": 188}
try:
    with open(SETTINGS_PATH, encoding="utf-8") as settings_file:
        SETTINGS = {**DEFAULTS, **json.load(settings_file)}
except (OSError, json.JSONDecodeError):
    SETTINGS = DEFAULTS
API_URL = os.getenv("BANK_ACTIVITY_URL", SETTINGS["server_url"])
POLL_MS = max(1, int(SETTINGS["poll_seconds"])) * 1000
DISPLAY_MS = max(1, int(SETTINGS["display_seconds"])) * 1000
WIDTH, HEIGHT = max(360, int(SETTINGS["popup_width"])), max(188, int(SETTINGS["popup_height"]))
MAX_ALERTS = max(1, min(5, int(SETTINGS["max_alerts"])))

def log(message):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as output:
            output.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")
    except OSError:
        pass

def active_work_area(root):
    """Use the monitor under the user's mouse, not a fixed primary display."""
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]
    point = POINT(root.winfo_pointerx(), root.winfo_pointery())
    monitor = ctypes.windll.user32.MonitorFromPoint(point, 2)
    info = MONITORINFO(ctypes.sizeof(MONITORINFO))
    if monitor and ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


class Notifier:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.seen = set()
        self.ready = False
        self.windows = {}
        log(f"started api={API_URL}")
        self.root.after(0, self.poll)

    def poll(self):
        if not self.is_enabled():
            self.root.after(POLL_MS, self.poll)
            return
        try:
            with urlopen(API_URL, timeout=2) as response:
                data = json.loads(response.read().decode("utf-8"))
            rows = [dict(item, direction="CREDIT") for item in data.get("credits", [])]
            rows += [dict(item, direction="DEBIT") for item in data.get("debits", [])]
            rows += data.get("test_alerts", [])
            log(f"poll rows={len(rows)} tests={len(data.get('test_alerts', []))}")
            current_ids = {item["id"] for item in rows}
            if self.ready:
                for item in rows:
                    if item["id"] not in self.seen:
                        self.show(item)
            self.seen = current_ids
            self.ready = True
        except Exception as error:
            log(f"poll failed: {error}")
        self.root.after(POLL_MS, self.poll)

    def is_enabled(self):
        if not SETTINGS.get("enabled", True):
            return False
        paused_until = SETTINGS.get("paused_until")
        if not paused_until:
            return True
        try:
            return datetime.now(timezone.utc) >= datetime.fromisoformat(paused_until)
        except ValueError:
            return True

    def show(self, item):
        item_id = item["id"]
        if item_id in self.windows:
            return
        while len(self.windows) >= MAX_ALERTS:
            self.close(next(iter(self.windows)))
        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.attributes("-alpha", max(0.5, min(1.0, float(SETTINGS["opacity"]) / 100)))
        credit = item.get("direction") == "CREDIT"
        semantic = "#146C43" if credit else "#B42332"
        popup.configure(bg=NAVY, highlightbackground=GOLD, highlightthickness=3)
        popup.geometry(f"{WIDTH}x{HEIGHT}+0+0")
        frame = tk.Frame(popup, bg=NAVY, padx=16, pady=12)
        frame.pack(fill="both", expand=True)
        header = tk.Frame(frame, bg=NAVY); header.pack(fill="x")
        if os.path.exists(LOGO_PATH):
            try:
                logo = tk.PhotoImage(file=LOGO_PATH)
                logo = logo.subsample(max(1, logo.width() // 38), max(1, logo.height() // 34))
                logo_label = tk.Label(header, image=logo, bg=NAVY); logo_label.image = logo; logo_label.pack(side="left", padx=(0, 8))
            except tk.TclError:
                pass
        tk.Label(header, text="ARADHANA JEWELLERS", bg=NAVY, fg=LIGHT_GOLD, font=("Segoe UI", 8, "bold")).pack(side="left")
        tk.Label(header, text=f"NEW {item.get('direction', 'PAYMENT')}", bg=semantic, fg="white", font=("Segoe UI", 8, "bold"), padx=7, pady=2).pack(side="right")
        tk.Label(frame, text=f"₹{float(item.get('amount', 0)):,.2f}", bg=NAVY, fg=LIGHT_GOLD, font=("Segoe UI", 21, "bold")).pack(anchor="w", pady=(7, 0))
        tk.Label(frame, text=item.get("bank_name", "Bank not recorded"), bg=NAVY, fg="white", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        reference = item.get("reference", "Not recorded")
        row = tk.Frame(frame, bg=NAVY)
        row.pack(fill="x", pady=(10, 0))
        tk.Label(row, text=reference, bg=NAVY, fg="white", font=("Consolas", 9, "bold"), anchor="w").pack(side="left", fill="x", expand=True)
        tk.Button(row, text="COPY", command=lambda: self.copy(reference), font=("Segoe UI", 8, "bold"), bg=GOLD, fg=INK, activebackground=LIGHT_GOLD, relief="flat", padx=8).pack(side="right")
        tk.Button(frame, text="×", command=lambda: self.close(item_id), bg=NAVY, fg=LIGHT_GOLD, activebackground=NAVY, activeforeground="white", relief="flat", font=("Segoe UI", 12, "bold")).place(relx=1, x=-3, y=-8, anchor="ne")
        self.windows[item_id] = popup
        log(f"shown id={item_id} amount={item.get('amount', 0)}")
        if SETTINGS.get("sound") and float(item.get("amount", 0)) >= float(SETTINGS.get("sound_threshold", 100000)):
            self.root.bell()
        self.reposition()
        popup.after(DISPLAY_MS, lambda: self.close(item_id))

    def copy(self, value):
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update()

    def close(self, item_id):
        popup = self.windows.pop(item_id, None)
        if popup and popup.winfo_exists():
            popup.destroy()
        self.reposition()

    def reposition(self):
        """Keep the newest three notifications vertically stacked, never overlapping."""
        left, top, right, bottom = active_work_area(self.root)
        screen_x = right - WIDTH - 28
        count = len(self.windows)
        group_height = count * HEIGHT + max(0, count - 1) * 12
        if SETTINGS.get("position") == "bottom-right":
            start_y = bottom - group_height - 28
        else:
            start_y = max(top + 120, top + ((bottom - top - group_height) // 3))
        for index, popup in enumerate(self.windows.values()):
            if popup.winfo_exists():
                popup.geometry(f"{WIDTH}x{HEIGHT}+{screen_x}+{start_y + index * (HEIGHT + 12)}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Notifier().run()
