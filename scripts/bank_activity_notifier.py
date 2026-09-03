"""Always-on-top Windows transaction notifications without a browser.

Run this on any trusted LAN PC. Set BANK_ACTIVITY_URL to the Billing-PC API
URL when the notifier is not running on the Billing PC itself.
"""
import json
import os
import tkinter as tk
import ctypes
from datetime import datetime, timezone
from urllib.request import Request, urlopen

SETTINGS_PATH = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "AradhanaBankActivityNotifier", "settings.json")
LOG_PATH = os.path.join(os.path.dirname(SETTINGS_PATH), "runtime.log")
LOGO_PATH = r"C:\Content\Logos\Logo Dimensions in Reel 30% x=220 y=200.png"
if not os.path.exists(LOGO_PATH):
    LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
NAVY, GOLD, LIGHT_GOLD, INK = "#23519D", "#CCA137", "#F7CA5B", "#10254A"
DEFAULTS = {"server_url": "http://ARADHANA:8000/api/bank-activity", "poll_seconds": 1, "display_seconds": 30, "opacity": 92, "max_alerts": 3, "sound": False, "sound_threshold": 100000, "position": "centre-right", "enabled": True, "paused_until": None, "popup_width": 360, "popup_height": 188}
def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as settings_file:
            return {**DEFAULTS, **json.load(settings_file)}
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULTS)

SETTINGS = load_settings()
REPLAY_COUNT = max(0, int(os.getenv("BANK_ACTIVITY_REPLAY_COUNT", "0")))

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
        self.settings_mtime = None
        self.failure_count = 0
        log(f"started api={self.api_url}")
        self.root.after(0, self.poll)

    def poll(self):
        self.reload_settings()
        if not self.is_enabled():
            self.root.after(self.poll_ms, self.poll)
            return
        try:
            with urlopen(self.api_url, timeout=2) as response:
                data = json.loads(response.read().decode("utf-8"))
            rows = [dict(item, direction="CREDIT") for item in data.get("credits", [])]
            rows += [dict(item, direction="DEBIT") for item in data.get("debits", [])]
            rows += data.get("test_alerts", [])
            log(f"poll rows={len(rows)} tests={len(data.get('test_alerts', []))}")
            current_ids = {item["id"] for item in rows}
            if not self.ready and REPLAY_COUNT:
                # Explicit local replay for operator review. Never posts data
                # back to the server and exits once the popups have elapsed.
                for item in rows[:REPLAY_COUNT]:
                    self.show(item)
                self.root.after(self.display_ms + 1000, self.root.destroy)
            if self.ready:
                for item in rows:
                    if item["id"] not in self.seen:
                        self.show(item)
            self.seen = current_ids
            self.ready = True
            if self.failure_count:
                log("poll recovered")
                self.failure_count = 0
        except Exception as error:
            self.failure_count += 1
            if self.failure_count in (1, 5, 30):
                log(f"poll failed count={self.failure_count}: {error}")
        self.root.after(self.poll_ms, self.poll)

    @property
    def api_url(self):
        return os.getenv("BANK_ACTIVITY_URL", SETTINGS["server_url"])

    @property
    def poll_ms(self):
        return max(1, int(SETTINGS["poll_seconds"])) * 1000

    @property
    def display_ms(self):
        return max(1, int(SETTINGS["display_seconds"])) * 1000

    @property
    def width(self):
        return max(360, int(SETTINGS["popup_width"]))

    @property
    def height(self):
        return max(188, int(SETTINGS["popup_height"]))

    @property
    def max_alerts(self):
        return max(1, min(5, int(SETTINGS["max_alerts"])))

    def reload_settings(self):
        global SETTINGS
        try:
            mtime = os.path.getmtime(SETTINGS_PATH)
        except OSError:
            mtime = None
        if mtime != self.settings_mtime:
            SETTINGS = load_settings()
            self.settings_mtime = mtime
            log(f"settings reloaded api={self.api_url}")

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
        while len(self.windows) >= self.max_alerts:
            self.close(next(iter(self.windows)))
        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.attributes("-alpha", max(0.5, min(1.0, float(SETTINGS["opacity"]) / 100)))
        credit = item.get("direction") == "CREDIT"
        semantic = "#146C43" if credit else "#B42332"
        popup.configure(bg=NAVY, highlightbackground=GOLD, highlightthickness=3)
        popup.geometry(f"{self.width}x{self.height}+0+0")
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
        party_name = str(item.get("counterparty") or item.get("payer_name") or "BANK TRANSACTION").strip()
        tk.Label(header, text=party_name[:34].upper(), bg=NAVY, fg=LIGHT_GOLD, font=("Segoe UI", 8, "bold")).pack(side="left")
        tk.Label(header, text=f"NEW {item.get('direction', 'PAYMENT')}", bg=semantic, fg="white", font=("Segoe UI", 8, "bold"), padx=7, pady=2).pack(side="right")
        tk.Label(frame, text=f"₹{float(item.get('amount', 0)):,.2f}", bg=NAVY, fg=LIGHT_GOLD, font=("Segoe UI", 21, "bold")).pack(anchor="w", pady=(7, 0))
        tk.Label(frame, text=item.get("bank_name", "Bank not recorded"), bg=NAVY, fg="white", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        reference = item.get("reference", "Not recorded")
        row = tk.Frame(frame, bg=NAVY)
        row.pack(fill="x", pady=(10, 0))
        copy_colours = {"blue": "#2563EB", "green": "#15803D", "red": "#DC2626"}
        copy_state = item.get("copy_state", "blue")
        copy_colour = copy_colours.get(copy_state, copy_colours["blue"])
        reference_label = tk.Label(row, text=reference, bg=NAVY, fg=copy_colour, font=("Consolas", 9, "bold"), anchor="w")
        reference_label.pack(side="left", fill="x", expand=True)
        copy_button = tk.Button(row, text="COPY", font=("Segoe UI", 8, "bold"), bg=copy_colour, fg="white", activebackground=copy_colour, relief="flat", padx=8)
        copy_button.configure(command=lambda: self.copy(item, reference_label, copy_button))
        copy_button.pack(side="right")
        tk.Button(frame, text="×", command=lambda: self.close(item_id), bg=NAVY, fg=LIGHT_GOLD, activebackground=NAVY, activeforeground="white", relief="flat", font=("Segoe UI", 12, "bold")).place(relx=1, x=-3, y=-8, anchor="ne")
        self.windows[item_id] = popup
        log(f"shown id={item_id} amount={item.get('amount', 0)}")
        if SETTINGS.get("sound") and float(item.get("amount", 0)) >= float(SETTINGS.get("sound_threshold", 100000)):
            self.root.bell()
        self.reposition()
        popup.after(self.display_ms, lambda: self.close(item_id))

    def copy(self, item, reference_label, copy_button):
        value = str(item.get("reference", "")).strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update()
        if not value or value.lower() == "not recorded":
            return
        endpoint = f"{self.api_url.rstrip('/').rsplit('/api/bank-activity', 1)[0]}/api/bank-activity/reference-copied"
        try:
            request = Request(endpoint, data=json.dumps({"reference": value, "source": "popup"}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=2) as response:
                state = json.loads(response.read().decode("utf-8"))
            colour = {"blue": "#2563EB", "green": "#15803D", "red": "#DC2626"}.get(state.get("copy_state"), "#2563EB")
            item["copy_count"] = state.get("copy_count", 0)
            item["copy_state"] = state.get("copy_state", "blue")
            reference_label.configure(fg=colour)
            copy_button.configure(bg=colour, activebackground=colour)
            log(f"reference copied state={item['copy_state']} reference={value}")
        except Exception as error:
            log(f"reference copy state failed: {error}")

    def close(self, item_id):
        popup = self.windows.pop(item_id, None)
        if popup and popup.winfo_exists():
            popup.destroy()
        self.reposition()

    def reposition(self):
        """Keep the newest three notifications vertically stacked, never overlapping."""
        left, top, right, bottom = active_work_area(self.root)
        screen_x = right - self.width - 28
        count = len(self.windows)
        group_height = count * self.height + max(0, count - 1) * 12
        if SETTINGS.get("position") == "bottom-right":
            start_y = bottom - group_height - 28
        else:
            start_y = max(top + 120, top + ((bottom - top - group_height) // 3))
        for index, popup in enumerate(self.windows.values()):
            if popup.winfo_exists():
                popup.geometry(f"{self.width}x{self.height}+{screen_x}+{start_y + index * (self.height + 12)}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Notifier().run()
