"""Always-on-top Windows transaction notifications without a browser.

Run this on any trusted LAN PC. Set BANK_ACTIVITY_URL to the Billing-PC API
URL when the notifier is not running on the Billing PC itself.
"""
import json
import os
import tkinter as tk
import ctypes
import hashlib
import re
import subprocess
from datetime import datetime, timezone
from urllib.request import Request, urlopen

SETTINGS_PATH = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "AradhanaBankActivityNotifier", "settings.json")
LOG_PATH = os.path.join(os.path.dirname(SETTINGS_PATH), "runtime.log")
LOGO_PATH = r"C:\Content\Logos\Logo Dimensions in Reel 30% x=220 y=200.png"
if not os.path.exists(LOGO_PATH):
    LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
NAVY, GOLD, LIGHT_GOLD, INK = "#23519D", "#CCA137", "#F7CA5B", "#10254A"
DEFAULTS = {"server_url": "http://ARADHANA:8000/api/bank-activity", "poll_seconds": 1, "display_seconds": 30, "opacity": 92, "max_alerts": 3, "sound": False, "sound_threshold": 100000, "position": "centre-right", "enabled": True, "paused_until": None, "popup_width": 360, "popup_height": 188}
UPDATE_CHECK_MS = 15 * 60 * 1000

def _bounded_int(value, default, minimum, maximum):
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default

def _bounded_float(value, default, minimum):
    try:
        return max(minimum, float(value))
    except (TypeError, ValueError):
        return default

def _as_bool(value, default):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "1", "yes", "on"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("false", "0", "no", "off"):
        return False
    return default

def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as settings_file:
            raw = json.load(settings_file)
    except (OSError, json.JSONDecodeError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    server_url = str(raw.get("server_url", DEFAULTS["server_url"])).strip()
    paused_until = raw.get("paused_until")
    try:
        if paused_until:
            datetime.fromisoformat(str(paused_until))
    except ValueError:
        paused_until = None
    return {
        "server_url": server_url if server_url.startswith(("http://", "https://")) else DEFAULTS["server_url"],
        "poll_seconds": _bounded_int(raw.get("poll_seconds"), DEFAULTS["poll_seconds"], 1, 60),
        "display_seconds": _bounded_int(raw.get("display_seconds"), DEFAULTS["display_seconds"], 1, 300),
        "opacity": _bounded_int(raw.get("opacity"), DEFAULTS["opacity"], 50, 100),
        "max_alerts": _bounded_int(raw.get("max_alerts"), DEFAULTS["max_alerts"], 1, 5),
        "sound": _as_bool(raw.get("sound"), DEFAULTS["sound"]),
        "sound_threshold": _bounded_float(raw.get("sound_threshold"), DEFAULTS["sound_threshold"], 0),
        "position": raw.get("position") if raw.get("position") in ("centre-right", "bottom-right") else DEFAULTS["position"],
        "enabled": _as_bool(raw.get("enabled"), DEFAULTS["enabled"]),
        "paused_until": paused_until,
        "popup_width": _bounded_int(raw.get("popup_width"), DEFAULTS["popup_width"], 360, 1200),
        "popup_height": _bounded_int(raw.get("popup_height"), DEFAULTS["popup_height"], 188, 900),
    }

SETTINGS = load_settings()
REPLAY_COUNT = max(0, int(os.getenv("BANK_ACTIVITY_REPLAY_COUNT", "0")))

def log(message):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as output:
            output.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")
    except OSError:
        pass

def reference_only(value):
    """Return only the transaction identifier; never copy labels or popup text."""
    raw = str(value or "").strip()
    labelled = re.search(r"(?:utr|ref(?:erence)?|txn|transaction)\s*(?:no|number|id)?\s*[:#-]*\s*([A-Za-z0-9][A-Za-z0-9/-]{5,})", raw, re.IGNORECASE)
    if labelled:
        return labelled.group(1)
    candidates = re.findall(r"(?<![A-Za-z0-9])[A-Za-z0-9][A-Za-z0-9/-]{5,}(?![A-Za-z0-9])", raw)
    numeric_candidates = [candidate for candidate in candidates if any(char.isdigit() for char in candidate)]
    return (numeric_candidates[-1] if numeric_candidates else raw.splitlines()[0]).strip()


def _version_key(value):
    """Comparable numeric version; malformed manifests never trigger an update."""
    try:
        return tuple(int(part) for part in str(value).strip().split("."))
    except ValueError:
        return ()


def _update_manifest_url(api_url):
    root = api_url.rstrip("/").rsplit("/api/bank-activity", 1)[0]
    return f"{root}/api/bank-activity/notifier-release"


def _download_update(manifest, destination):
    url = str(manifest.get("download_url") or "").strip()
    digest = str(manifest.get("sha256") or "").strip().lower()
    if not url.startswith(("http://", "https://")) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("release manifest is incomplete")
    request = Request(url, headers={"User-Agent": "AradhanaBankNotifier"})
    hasher = hashlib.sha256()
    with urlopen(request, timeout=20) as response, open(destination, "wb") as output:
        while True:
            block = response.read(1024 * 256)
            if not block:
                break
            hasher.update(block)
            output.write(block)
    if hasher.hexdigest().lower() != digest:
        try:
            os.remove(destination)
        except OSError:
            pass
        raise ValueError("release checksum did not match")


def install_available_update(api_url):
    """Stage a verified newer EXE and let it replace this notifier atomically."""
    current_version = _version_key(os.getenv("BANK_NOTIFIER_VERSION", "0"))
    current_exe = os.getenv("BANK_NOTIFIER_EXECUTABLE", "")
    if not current_exe or not os.path.isfile(current_exe):
        return False
    with urlopen(_update_manifest_url(api_url), timeout=3) as response:
        manifest = json.loads(response.read().decode("utf-8"))
    target_version = _version_key(manifest.get("version"))
    if not target_version or target_version <= current_version:
        return False
    update_dir = os.path.join(os.getenv("LOCALAPPDATA", os.path.expanduser("~")), "AradhanaBankActivityNotifier", "updates")
    os.makedirs(update_dir, exist_ok=True)
    staged = os.path.join(update_dir, f"AradhanaBankActivityNotifier-{manifest['version']}.exe")
    _download_update(manifest, staged)
    log(f"verified update {manifest['version']}; installing")
    subprocess.Popen([staged, "--update"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return True

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
        self.root.after(UPDATE_CHECK_MS, self.check_for_update)

    def check_for_update(self):
        try:
            if install_available_update(self.api_url):
                self.root.after(1000, self.root.destroy)
                return
        except Exception as error:
            # Update availability must never interrupt payment notifications.
            log(f"update check skipped: {error}")
        self.root.after(UPDATE_CHECK_MS, self.check_for_update)

    def poll(self):
        try:
            self.reload_settings()
            if not self.is_enabled():
                return
            with urlopen(self.api_url, timeout=2) as response:
                data = json.loads(response.read().decode("utf-8"))
            rows = [dict(item, direction="CREDIT") for item in data.get("credits", [])]
            rows += [dict(item, direction="DEBIT") for item in data.get("debits", [])]
            rows += data.get("test_alerts", [])
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
            else:
                # A currently-active test alert must display even when this
                # notifier was started after the test was sent.
                for item in data.get("test_alerts", []):
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
        finally:
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
        # Reserve room for the close control and the status badge.  At the
        # minimum supported popup width this prevents "NEW CREDIT" clipping.
        tk.Button(header, text="×", command=lambda: self.close(item_id), bg=NAVY, fg=LIGHT_GOLD,
                  activebackground=NAVY, activeforeground="white", relief="flat",
                  font=("Segoe UI", 12, "bold"), padx=2, pady=0).pack(side="right")
        tk.Label(header, text=f"NEW {item.get('direction', 'PAYMENT')}", bg=semantic, fg="white",
                 font=("Segoe UI", 8, "bold"), padx=7, pady=2).pack(side="right", padx=(0, 6))
        tk.Label(header, text=party_name[:23].upper(), bg=NAVY, fg=LIGHT_GOLD,
                 font=("Segoe UI", 8, "bold"), anchor="w").pack(side="left", fill="x", expand=True)
        tk.Label(frame, text=f"₹{float(item.get('amount', 0)):,.2f}", bg=NAVY, fg=LIGHT_GOLD, font=("Segoe UI", 21, "bold")).pack(anchor="w", pady=(7, 0))
        tk.Label(frame, text=item.get("bank_name", "Bank not recorded"), bg=NAVY, fg="white", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        reference = reference_only(item.get("reference", "Not recorded"))
        row = tk.Frame(frame, bg=NAVY)
        row.pack(fill="x", pady=(10, 0))
        copy_colours = {"blue": "#2563EB", "green": "#15803D", "red": "#DC2626"}
        copy_state = item.get("copy_state", "blue")
        copy_colour = copy_colours.get(copy_state, copy_colours["blue"])
        # The state stays visible on the COPY button.  Keep the reference
        # itself white so it is readable against every popup colour/opacity.
        reference_label = tk.Label(row, text=reference, bg=NAVY, fg="white", font=("Consolas", 9, "bold"), anchor="w")
        reference_label.pack(side="left", fill="x", expand=True)
        copy_button = tk.Button(row, text="COPY", font=("Segoe UI", 8, "bold"), bg=copy_colour, fg="white", activebackground=copy_colour, relief="flat", padx=8)
        copy_button.configure(command=lambda: self.copy(item, reference_label, copy_button))
        copy_button.pack(side="right")
        self.windows[item_id] = popup
        log(f"shown id={item_id} amount={item.get('amount', 0)}")
        if SETTINGS.get("sound") and float(item.get("amount", 0)) >= float(SETTINGS.get("sound_threshold", 100000)):
            self.root.bell()
        self.reposition()
        popup.after(self.display_ms, lambda: self.close(item_id))

    def copy(self, item, reference_label, copy_button):
        value = reference_only(item.get("reference", ""))
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
