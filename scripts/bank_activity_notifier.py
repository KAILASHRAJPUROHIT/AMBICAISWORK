"""Always-on-top Windows transaction notifications without a browser.

Run this on any trusted LAN PC. Set BANK_ACTIVITY_URL to the Billing-PC API
URL when the notifier is not running on the Billing PC itself.
"""
import json
import os
import tkinter as tk
import ctypes
import ctypes.wintypes as wintypes
import hashlib
import queue
import re
import subprocess
import threading
from datetime import datetime, timezone
from urllib.request import Request, urlopen

SETTINGS_PATH = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "AradhanaBankActivityNotifier", "settings.json")
LOG_PATH = os.path.join(os.path.dirname(SETTINGS_PATH), "runtime.log")
LOGO_PATH = r"C:\Content\Logos\Logo Dimensions in Reel 30% x=220 y=200.png"
if not os.path.exists(LOGO_PATH):
    LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
# Sampled directly from the approved verification-card reference design.
NAVY, GOLD, LIGHT_GOLD, INK = "#23519D", "#D9B54A", "#FDDF83", "#0B2050"
CARD_WASH = "#1B4B9E"
CREDIT_GREEN, DEBIT_RED, COPY_BLUE = "#116741", "#B42332", "#0B4FC9"
# A colour nobody would deliberately use in the popup itself, set as the
# window's -transparentcolor so a Canvas-drawn rounded rectangle is the
# only thing visible - everything outside the rounded shape (including the
# Toplevel's own square corners) shows the desktop through instead.
CORNER_KEY = "#0a0a0a"
POPUP_RADIUS = 18
DEFAULTS = {"server_url": "http://ARADHANA:8000/api/bank-activity", "notifier_token": "", "poll_seconds": 1, "display_seconds": 30, "opacity": 92, "max_alerts": 3, "sound": False, "sound_threshold": 100000, "position": "centre-right", "enabled": True, "paused_until": None, "popup_width": 360, "popup_height": 188}
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
        "notifier_token": str(raw.get("notifier_token", DEFAULTS["notifier_token"])).strip(),
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


def _rounded_rect_points(x0, y0, x1, y1, radius):
    """Point list for a Canvas smooth polygon that reads as a true rounded
    rectangle rather than an octagon - smooth=True quadratic-interpolates
    between these, so only the corners need extra points."""
    return [
        x0 + radius, y0,
        x1 - radius, y0,
        x1, y0,
        x1, y0 + radius,
        x1, y1 - radius,
        x1, y1,
        x1 - radius, y1,
        x0 + radius, y1,
        x0, y1,
        x0, y1 - radius,
        x0, y0 + radius,
        x0, y0,
        x0 + radius, y0,
    ]


class GlobalHotkeyListener:
    """System-wide Alt+F1, working no matter which application has focus.

    Tkinter has no concept of a global hotkey - only RegisterHotKey (a raw
    Win32 call) can claim one across every application. That call delivers
    WM_HOTKEY through a normal Windows message loop, so this runs its own
    tiny message-only window on a background thread (never touching
    Tkinter's own loop, which isn't thread-safe) and hands the result to
    the caller through a queue for the Tkinter mainloop to pick up safely.
    """
    WM_HOTKEY = 0x0312
    MOD_ALT = 0x0001
    VK_F1 = 0x70
    HOTKEY_ID = 1

    def __init__(self, on_triggered):
        self.on_triggered = on_triggered
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            WNDPROCTYPE = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)

            # Without explicit argtypes, ctypes guesses each argument's width
            # from the Python value alone - on 64-bit Windows a handle/
            # pointer value routinely exceeds what that guess assumes,
            # raising "OverflowError: int too long to convert" even though
            # the call itself would have been perfectly valid. Declaring the
            # real Win32 signatures makes ctypes marshal every handle
            # correctly regardless of its numeric size.
            user32.DefWindowProcW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
            user32.DefWindowProcW.restype = ctypes.c_long
            user32.RegisterClassW.argtypes = [ctypes.c_void_p]
            user32.RegisterClassW.restype = wintypes.ATOM
            user32.CreateWindowExW.argtypes = [
                wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
            ]
            user32.CreateWindowExW.restype = wintypes.HWND
            user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            user32.RegisterHotKey.restype = wintypes.BOOL
            user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
            user32.GetMessageW.restype = ctypes.c_int
            user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
            user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
            kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
            kernel32.GetModuleHandleW.restype = wintypes.HMODULE

            def wndproc(hwnd, msg, wparam, lparam):
                if msg == self.WM_HOTKEY and wparam == self.HOTKEY_ID:
                    self.on_triggered()
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

            self._wndproc_ref = WNDPROCTYPE(wndproc)  # kept alive on self

            class WNDCLASS(ctypes.Structure):
                _fields_ = [
                    ("style", ctypes.c_uint), ("lpfnWndProc", WNDPROCTYPE), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
                ]

            class_name = "AradhanaBankActivityHotkeyWindow"
            wndclass = WNDCLASS()
            wndclass.lpfnWndProc = self._wndproc_ref
            wndclass.hInstance = kernel32.GetModuleHandleW(None)
            wndclass.lpszClassName = class_name
            user32.RegisterClassW(ctypes.byref(wndclass))

            hwnd = user32.CreateWindowExW(0, class_name, "AradhanaHotkey", 0, 0, 0, 0, 0, None, None, wndclass.hInstance, None)
            if not hwnd:
                log("global hotkey window creation failed; Alt+F1 unavailable")
                return
            if not user32.RegisterHotKey(hwnd, self.HOTKEY_ID, self.MOD_ALT, self.VK_F1):
                log("RegisterHotKey(Alt+F1) failed - likely already claimed by another app")
                return

            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as error:
            log(f"global hotkey listener stopped: {error}")


class Notifier:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.seen = set()
        self.ready = False
        self.windows = {}
        self.settings_mtime = None
        self.failure_count = 0
        self.last_real_item = None
        # Alt+F1 works from any application, not just when a popup has
        # focus - see GlobalHotkeyListener. It runs on its own thread and
        # can never touch Tkinter directly, so it just drops a token in this
        # queue; _poll_hotkey_queue (on the Tkinter mainloop) is what
        # actually acts on it.
        self._hotkey_queue = queue.Queue()
        self.hotkey_listener = GlobalHotkeyListener(on_triggered=lambda: self._hotkey_queue.put(True))
        log(f"started api={self.api_url}")
        self.root.after(0, self.poll)
        self.root.after(UPDATE_CHECK_MS, self.check_for_update)
        self.root.after(150, self._poll_hotkey_queue)

    def _poll_hotkey_queue(self):
        triggered = False
        while True:
            try:
                self._hotkey_queue.get_nowait()
                triggered = True
            except queue.Empty:
                break
        if triggered:
            self.redisplay_last()
        self.root.after(150, self._poll_hotkey_queue)

    def redisplay_last(self):
        """Alt+F1: copy the most recent real payment's txn id and bring its
        popup back for exactly 10 seconds, regardless of whether it already
        closed or what the configured display_seconds is."""
        if not self.last_real_item:
            log("Alt+F1 pressed but no payment has been shown yet this session")
            return
        item = self.last_real_item
        reference = reference_only(item.get("reference", ""))
        if reference and reference.lower() != "not recorded":
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(reference)
                self.root.update()
                log(f"Alt+F1: copied last txn id to clipboard ({reference})")
            except tk.TclError as error:
                log(f"Alt+F1: clipboard copy failed: {error}")
        item_id = item["id"]
        if item_id in self.windows:
            self.close(item_id)
        self.show(item, force_duration_ms=10000)

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
            request = Request(self.api_url, headers=self._auth_headers())
            with urlopen(request, timeout=2) as response:
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
    def notifier_token(self):
        return os.getenv("BANK_ACTIVITY_TOKEN", SETTINGS.get("notifier_token", ""))

    def _auth_headers(self, extra=None):
        headers = dict(extra or {})
        if self.notifier_token:
            headers["X-Notifier-Token"] = self.notifier_token
        return headers

    @property
    def poll_ms(self):
        return max(1, int(SETTINGS["poll_seconds"])) * 1000

    @property
    def display_ms(self):
        return max(1, int(SETTINGS["display_seconds"])) * 1000

    @property
    def width(self):
        return max(380, int(SETTINGS["popup_width"]))

    @property
    def height(self):
        return max(234, int(SETTINGS["popup_height"]))

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

    def show(self, item, force_duration_ms=None):
        item_id = item["id"]
        if item_id in self.windows:
            return
        while len(self.windows) >= self.max_alerts:
            self.close(next(iter(self.windows)))

        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.attributes("-alpha", max(0.5, min(1.0, float(SETTINGS["opacity"]) / 100)))
        popup.configure(bg=CORNER_KEY)
        try:
            # Windows-only: makes CORNER_KEY pixels see-through, so only the
            # rounded shape drawn on the canvas below is actually visible -
            # everything outside it (including the Toplevel's own square
            # corners) shows the desktop through instead.
            popup.wm_attributes("-transparentcolor", CORNER_KEY)
        except tk.TclError:
            pass
        popup.geometry(f"{self.width}x{self.height}+0+0")

        credit = item.get("direction") == "CREDIT"
        semantic = CREDIT_GREEN if credit else DEBIT_RED

        canvas = tk.Canvas(popup, width=self.width, height=self.height, bg=CORNER_KEY, highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        # Base fill first (no border yet), then a soft lighter wash confined
        # well inside the card bounds so it reads as a gradient rather than a
        # flat block, then the gold border drawn on top of both so it stays
        # crisp - matches the verification-card reference without an image.
        canvas.create_polygon(
            _rounded_rect_points(2, 2, self.width - 2, self.height - 2, POPUP_RADIUS),
            smooth=True, fill=INK, outline="",
        )
        canvas.create_oval(6, 6, self.width * 0.7, self.height * 0.65,
                            fill=CARD_WASH, outline="", stipple="gray50")
        canvas.create_polygon(
            _rounded_rect_points(2, 2, self.width - 2, self.height - 2, POPUP_RADIUS),
            smooth=True, fill="", outline=GOLD, width=2,
        )
        # Thin diagonal gold accent line sweeping the lower-right corner.
        canvas.create_line(self.width - 34, self.height * 0.28, self.width * 0.45, self.height - 6,
                            fill=GOLD, width=1)

        content = tk.Frame(canvas, bg=INK)
        canvas.create_window(18, 14, window=content, anchor="nw", width=self.width - 36, height=self.height - 28)

        header = tk.Frame(content, bg=INK); header.pack(fill="x")
        if os.path.exists(LOGO_PATH):
            try:
                logo = tk.PhotoImage(file=LOGO_PATH)
                logo = logo.subsample(max(1, logo.width() // 40), max(1, logo.height() // 36))
                logo_label = tk.Label(header, image=logo, bg=INK); logo_label.image = logo; logo_label.pack(side="left", padx=(0, 8))
            except tk.TclError:
                pass
        title_col = tk.Frame(header, bg=INK); title_col.pack(side="left", fill="x", expand=True)
        # Reserve room for the close control and the status badge.  At the
        # minimum supported popup width this prevents "NEW CREDIT" clipping.
        tk.Button(header, text="×", command=lambda: self.close(item_id), bg=INK, fg=LIGHT_GOLD,
                  activebackground=INK, activeforeground="white", relief="flat",
                  font=("Segoe UI", 13, "bold"), padx=2, pady=0).pack(side="right", anchor="n")
        tk.Label(header, text=f"NEW {item.get('direction', 'PAYMENT')}", bg=semantic, fg="white",
                 font=("Segoe UI", 8, "bold"), padx=7, pady=2).pack(side="right", padx=(0, 6), anchor="n")
        tk.Label(title_col, text="PAYMENT VERIFIED", bg=INK, fg=LIGHT_GOLD,
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x")
        tk.Label(title_col, text="TRANSACTION SUCCESSFUL", bg=INK, fg="#8EA3C7",
                 font=("Segoe UI", 7, "bold"), anchor="w").pack(fill="x")

        tk.Label(content, text=f"₹{float(item.get('amount', 0)):,.2f}", bg=INK, fg=LIGHT_GOLD,
                 font=("Segoe UI", 25, "bold")).pack(anchor="w", pady=(10, 0))
        party_name = str(item.get("counterparty") or item.get("payer_name") or "BANK TRANSACTION").strip()
        name_row = tk.Frame(content, bg=INK); name_row.pack(fill="x")
        tk.Label(name_row, text=party_name[:23].upper(), bg=INK, fg="white",
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Label(name_row, text=f"  ·  {item.get('bank_name', 'Bank not recorded')}", bg=INK, fg="#8EA3C7",
                 font=("Segoe UI", 8, "bold")).pack(side="left")

        reference = reference_only(item.get("reference", "Not recorded"))
        copy_colours = {"blue": COPY_BLUE, "green": "#15803D", "red": "#DC2626"}
        copy_state = item.get("copy_state", "blue")
        copy_colour = copy_colours.get(copy_state, copy_colours["blue"])
        tk.Label(content, text="TXN ID", bg=INK, fg=GOLD, font=("Segoe UI", 7, "bold"),
                 anchor="w").pack(fill="x", pady=(13, 0))
        row = tk.Frame(content, bg=INK)
        row.pack(fill="x", pady=(3, 0))
        # The state stays visible on the COPY button.  Keep the reference
        # itself white so it is readable against every popup colour/opacity.
        reference_label = tk.Label(row, text=reference, bg=INK, fg="white", font=("Consolas", 10, "bold"), anchor="w")
        reference_label.pack(side="left", fill="x", expand=True)
        copy_button = tk.Button(row, text="⧉  COPY", font=("Segoe UI", 9, "bold"), bg=copy_colour, fg="white",
                                 activebackground=copy_colour, relief="flat", padx=14, pady=5)
        copy_button.configure(command=lambda: self.copy(item, reference_label, copy_button))
        copy_button.pack(side="right")

        self.windows[item_id] = popup
        if not str(item_id).startswith("test-"):
            self.last_real_item = item
        log(f"shown id={item_id} amount={item.get('amount', 0)}")
        if SETTINGS.get("sound") and float(item.get("amount", 0)) >= float(SETTINGS.get("sound_threshold", 100000)):
            self.root.bell()
        self.reposition()
        duration = force_duration_ms if force_duration_ms is not None else self.display_ms
        popup.after(duration, lambda: self.close(item_id))

    def copy(self, item, reference_label, copy_button):
        value = reference_only(item.get("reference", ""))
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update()
        if not value or value.lower() == "not recorded":
            return
        endpoint = f"{self.api_url.rstrip('/').rsplit('/api/bank-activity', 1)[0]}/api/bank-activity/reference-copied"
        try:
            request = Request(endpoint, data=json.dumps({"reference": value, "source": "popup"}).encode("utf-8"), headers=self._auth_headers({"Content-Type": "application/json"}), method="POST")
            with urlopen(request, timeout=2) as response:
                state = json.loads(response.read().decode("utf-8"))
            colour = {"blue": COPY_BLUE, "green": "#15803D", "red": "#DC2626"}.get(state.get("copy_state"), COPY_BLUE)
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
