"""Always-on-top Windows transaction notifications without a browser.

Run this on any trusted LAN PC. Set BANK_ACTIVITY_URL to the Billing-PC API
URL when the notifier is not running on the Billing PC itself.
"""
import json
import os
import tkinter as tk
from urllib.request import urlopen

SETTINGS_PATH = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "AradhanaBankActivityNotifier", "settings.json")
DEFAULTS = {"server_url": "http://127.0.0.1:8000/api/bank-activity", "poll_seconds": 1, "display_seconds": 30, "opacity": 92, "max_alerts": 3, "sound": False, "sound_threshold": 100000, "position": "centre-right"}
try:
    with open(SETTINGS_PATH, encoding="utf-8") as settings_file:
        SETTINGS = {**DEFAULTS, **json.load(settings_file)}
except (OSError, json.JSONDecodeError):
    SETTINGS = DEFAULTS
API_URL = os.getenv("BANK_ACTIVITY_URL", SETTINGS["server_url"])
POLL_MS = max(1, int(SETTINGS["poll_seconds"])) * 1000
DISPLAY_MS = max(1, int(SETTINGS["display_seconds"])) * 1000
WIDTH, HEIGHT = 360, 188
MAX_ALERTS = max(1, min(5, int(SETTINGS["max_alerts"])))


class Notifier:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.seen = set()
        self.ready = False
        self.windows = {}
        self.root.after(0, self.poll)

    def poll(self):
        try:
            with urlopen(API_URL, timeout=2) as response:
                data = json.loads(response.read().decode("utf-8"))
            rows = [dict(item, direction="CREDIT") for item in data.get("credits", [])]
            rows += [dict(item, direction="DEBIT") for item in data.get("debits", [])]
            current_ids = {item["id"] for item in rows}
            if self.ready:
                for item in rows:
                    if item["id"] not in self.seen:
                        self.show(item)
            self.seen = current_ids
            self.ready = True
        except Exception:
            # Remain silent while the local server is restarting or unavailable.
            pass
        self.root.after(POLL_MS, self.poll)

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
        background = "#e8f8ef" if credit else "#fff0f1"
        accent = "#047857" if credit else "#be123c"
        popup.configure(bg=background, highlightbackground=accent, highlightthickness=2)
        popup.geometry(f"{WIDTH}x{HEIGHT}+0+0")
        frame = tk.Frame(popup, bg=background, padx=16, pady=12)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=f"NEW {item.get('direction', 'PAYMENT')}", bg=background, fg=accent, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Label(frame, text=f"₹{float(item.get('amount', 0)):,.2f}", bg=background, fg="#111827", font=("Segoe UI", 21, "bold")).pack(anchor="w")
        tk.Label(frame, text=item.get("bank_name", "Bank not recorded"), bg=background, fg="#1f2937", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        reference = item.get("reference", "Not recorded")
        row = tk.Frame(frame, bg=background)
        row.pack(fill="x", pady=(10, 0))
        tk.Label(row, text=reference, bg=background, fg="#111827", font=("Consolas", 9, "bold"), anchor="w").pack(side="left", fill="x", expand=True)
        tk.Button(row, text="Copy", command=lambda: self.copy(reference), font=("Segoe UI", 8, "bold"), bg="#111827", fg="white", relief="flat", padx=8).pack(side="right")
        tk.Button(frame, text="×", command=lambda: self.close(item_id), bg=background, fg="#4b5563", relief="flat", font=("Segoe UI", 12, "bold")).place(relx=1, x=-3, y=-8, anchor="ne")
        self.windows[item_id] = popup
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
        screen_x = self.root.winfo_screenwidth() - WIDTH - 28
        count = len(self.windows)
        group_height = count * HEIGHT + max(0, count - 1) * 12
        start_y = max(120, (self.root.winfo_screenheight() - group_height) // (2 if SETTINGS.get("position") == "bottom-right" else 3))
        for index, popup in enumerate(self.windows.values()):
            if popup.winfo_exists():
                popup.geometry(f"{WIDTH}x{HEIGHT}+{screen_x}+{start_y + index * (HEIGHT + 12)}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Notifier().run()
