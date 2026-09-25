"""Live tablet screen feed for the Operations dashboard (2026-09-25).

Streams the CaptureCam tablet's screen as H.264 (adb screenrecord, the same
technique scrcpy uses) to the dashboard, and injects taps/swipes/keys back into
the tablet. Stdlib only. Binds to 127.0.0.1 -- the catalogue app (which owns
login) proxies it at /api/tablet/*, so nothing here is reachable without the
dashboard session.

Must run in the LOGGED-IN USER's session (it needs that user's adb key, which
is what authorised the tablet's wireless debugging) -- not as a Windows
service. tools/install_tablet_feed_tasks.ps1 registers it as a logon task.

Wire format on /stream: repeated [type:u8][length:u32 big-endian][payload]
  1 = key frame   (Annex-B access unit, SPS+PPS+IDR)
  2 = delta frame (Annex-B access unit)
  3 = heartbeat   (empty)
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config" / "tablet_feed.json"
LOG_PATH = BASE / "logs" / "tablet_feed.log"
PACKAGE = "com.aradhana.capturecam"
PORT = int(os.environ.get("TABLET_FEED_PORT", "7670"))
LONG_SIDE = 1280
BIT_RATE = "6M"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
KEYS = {"back": "KEYCODE_BACK", "home": "KEYCODE_HOME", "recents": "KEYCODE_APP_SWITCH"}


def _log(message: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 512_000:
            LOG_PATH.replace(LOG_PATH.with_suffix(".log.1"))
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(time.strftime("%Y-%m-%d %H:%M:%S ") + message + "\n")
    except OSError:
        pass


def _find_adb() -> str:
    for candidate in (
        r"C:\platform-tools\adb.exe",
        str(BASE / "scrcpy" / "scrcpy-win64-v4.1" / "adb.exe"),
        shutil.which("adb") or "",
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return "adb"


ADB = _find_adb()


def _config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_serial(serial: str) -> None:
    try:
        data = _config()
        if data.get("serial") != serial:
            data["serial"] = serial
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def adb(*args: str, serial: str | None = None, timeout: float = 8.0, binary: bool = False):
    command = [ADB] + (["-s", serial] if serial else []) + list(args)
    try:
        done = subprocess.run(
            command, capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        _log(f"adb {' '.join(args)} failed: {exc}")
        return None
    if binary:
        return done.stdout
    return done.stdout.decode("utf-8", "replace")


_serial_cache = {"at": 0.0, "value": None}


def resolve_serial() -> str | None:
    """The tablet's adb serial: saved one if online, else any online device."""
    now = time.time()
    if now - _serial_cache["at"] < 3.0:
        return _serial_cache["value"]
    found = None
    listing = adb("devices", timeout=6) or ""
    online = [line.split()[0] for line in listing.splitlines()[1:] if line.strip().endswith("device")]
    saved = _config().get("serial")
    if saved and saved in online:
        found = saved
    elif online:
        found = sorted(online, key=lambda s: (":5555" not in s, s))[0]
    elif saved and re.match(r"^[\d.]+:\d+$", saved):
        adb("connect", saved, timeout=6)
        listing = adb("devices", timeout=6) or ""
        if any(line.startswith(saved) and line.strip().endswith("device") for line in listing.splitlines()):
            found = saved
    if found:
        _save_serial(found)
    _serial_cache.update(at=now, value=found)
    return found


_screen_cache = {"at": 0.0, "value": (2560, 1600)}


def screen_size(serial: str) -> tuple[int, int]:
    """Current (rotated) display size -- what `input tap` coordinates use."""
    now = time.time()
    if now - _screen_cache["at"] < 20.0:
        return _screen_cache["value"]
    out = adb("shell", "dumpsys window displays", serial=serial, timeout=10) or ""
    sizes = [(int(w), int(h)) for w, h in re.findall(r"cur=(\d+)x(\d+)", out)]
    if sizes:
        _screen_cache.update(at=now, value=max(sizes, key=lambda s: s[0] * s[1]))
    return _screen_cache["value"]


def stream_size(serial: str) -> str:
    w, h = screen_size(serial)
    if w >= h:
        sw, sh = LONG_SIDE, int(LONG_SIDE * h / w)
    else:
        sw, sh = int(LONG_SIDE * w / h), LONG_SIDE
    return f"{sw // 2 * 2}x{sh // 2 * 2}"


_status_cache = {"at": 0.0, "value": None}


def capturecam_running(serial: str) -> bool:
    now = time.time()
    if now - _status_cache["at"] < 3.0 and _status_cache["value"] is not None:
        return _status_cache["value"]
    pid = (adb("shell", f"pidof {PACKAGE}", serial=serial, timeout=6) or "").strip()
    running = bool(re.match(r"^\d+", pid))
    _status_cache.update(at=now, value=running)
    return running


# --------------------------------------------------------------------------
# Broadcast of the H.264 stream to any number of viewers


class Broadcaster:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.subscribers: list[queue.Queue] = []
        self.gop: list[bytes] = []  # messages since the last key frame (fast join)
        self.streaming = False
        self.last_frame_at = 0.0

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=240)
        with self.lock:
            for message in self.gop:
                q.put_nowait(message)
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def viewer_count(self) -> int:
        with self.lock:
            return len(self.subscribers)

    def publish(self, kind: int, payload: bytes) -> None:
        message = struct.pack(">BI", kind, len(payload)) + payload
        with self.lock:
            if kind == 1:
                self.gop = [message]
            elif self.gop:
                self.gop.append(message)
                if len(self.gop) > 400:  # no key frame for ages: drop, force a restart
                    self.gop = []
            self.last_frame_at = time.time()
            for q in list(self.subscribers):
                try:
                    q.put_nowait(message)
                except queue.Full:
                    # Slow viewer: drop its backlog; it resumes at the next key frame.
                    try:
                        while True:
                            q.get_nowait()
                    except queue.Empty:
                        pass


BROADCAST = Broadcaster()
_START_CODE = re.compile(b"\x00\x00\x00\x01|\x00\x00\x01")


def _split_nals(buffer: bytearray) -> list[bytes]:
    """Pop every COMPLETE NAL unit (with its start code) off the buffer."""
    starts = [m.start() for m in _START_CODE.finditer(buffer)]
    if len(starts) < 2:
        return []
    nals = [bytes(buffer[a:b]) for a, b in zip(starts, starts[1:])]
    del buffer[: starts[-1]]
    return nals


def _nal_type(nal: bytes) -> int:
    offset = 4 if nal[:4] == b"\x00\x00\x00\x01" else 3
    return nal[offset] & 0x1F if len(nal) > offset else -1


def producer_loop() -> None:
    """Runs screenrecord while anyone is watching; restarts it when it exits."""
    while True:
        if BROADCAST.viewer_count() == 0:
            time.sleep(0.3)
            continue
        serial = resolve_serial()
        if not serial:
            time.sleep(2.0)
            continue
        size = stream_size(serial)
        _log(f"stream start serial={serial} size={size}")
        command = [ADB, "-s", serial, "exec-out", "screenrecord", "--output-format=h264",
                   "--size", size, "--bit-rate", BIT_RATE, "--time-limit", "170", "-"]
        try:
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    creationflags=CREATE_NO_WINDOW)
        except OSError as exc:
            _log(f"screenrecord spawn failed: {exc}")
            time.sleep(2.0)
            continue
        BROADCAST.streaming = True
        buffer = bytearray()
        pending_sps_pps: list[bytes] = []
        param_sets: list[bytes] = []
        idle_since = None
        try:
            while True:
                chunk = proc.stdout.read1(65536) if hasattr(proc.stdout, "read1") else proc.stdout.read(65536)
                if not chunk:
                    break
                buffer.extend(chunk)
                for nal in _split_nals(buffer):
                    kind = _nal_type(nal)
                    if kind in (7, 8):
                        # screenrecord only emits SPS/PPS once per run, not before
                        # every IDR -- keep the latest so each key frame is
                        # self-contained for a viewer that joins mid-stream.
                        if kind == 7:
                            pending_sps_pps = []
                        pending_sps_pps.append(nal)
                        param_sets = list(pending_sps_pps)
                    elif kind == 5:
                        BROADCAST.publish(1, b"".join(param_sets) + nal)
                        pending_sps_pps = []
                    elif kind == 1:
                        BROADCAST.publish(2, nal)
                if BROADCAST.viewer_count() == 0:
                    idle_since = idle_since or time.time()
                    if time.time() - idle_since > 8.0:
                        break
                else:
                    idle_since = None
        except Exception as exc:  # noqa: BLE001
            _log(f"stream error: {exc}")
        finally:
            BROADCAST.streaming = False
            try:
                proc.kill()
            except OSError:
                pass
            with BROADCAST.lock:
                BROADCAST.gop = []
        time.sleep(0.5)


# --------------------------------------------------------------------------
# Input injection (normalised 0..1 coordinates -> device pixels)


def inject(payload: dict) -> tuple[bool, str]:
    serial = resolve_serial()
    if not serial:
        return False, "tablet not reachable"
    action = payload.get("action")
    width, height = screen_size(serial)

    def px(name: str, span: int) -> int:
        return int(min(max(float(payload.get(name, 0.5)), 0.0), 1.0) * (span - 1))

    if action == "tap":
        adb("shell", f"input tap {px('x', width)} {px('y', height)}", serial=serial, timeout=6)
    elif action == "swipe":
        ms = int(min(max(float(payload.get("ms", 300)), 100), 2000))
        adb("shell",
            f"input swipe {px('x1', width)} {px('y1', height)} {px('x2', width)} {px('y2', height)} {ms}",
            serial=serial, timeout=8)
    elif action == "key" and payload.get("key") in KEYS:
        adb("shell", f"input keyevent {KEYS[payload['key']]}", serial=serial, timeout=6)
    else:
        return False, "unsupported action"
    return True, "ok"


# --------------------------------------------------------------------------


def _reported_endpoint():
    """ip:port CaptureCam last reported after boot (data/tablet_adb_endpoint.json)."""
    try:
        rec = json.loads((BASE / "data" / "tablet_adb_endpoint.json").read_text(encoding="utf-8"))
        return {"ip": rec["ip"], "port": rec["port"], "reported_at": rec.get("reported_at")}
    except Exception:  # noqa: BLE001
        return None


class Handler(BaseHTTPRequestHandler):
    server_version = "TabletFeed/1"
    # HTTP/1.1 so /stream can use chunked transfer: with a close-delimited
    # HTTP/1.0 body the dashboard's proxy (requests/urllib3) waits for the
    # whole body -- i.e. forever -- before passing any data on.
    protocol_version = "HTTP/1.1"

    def _chunk(self, data: bytes) -> None:
        self.wfile.write(b"%x\r\n" % len(data) + data + b"\r\n")
        self.wfile.flush()

    def log_message(self, fmt, *args):  # noqa: D401 -- keep the console quiet
        pass

    def _local_only(self) -> bool:
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            self.send_error(403)
            return False
        return True

    def _json(self, value: dict, code: int = 200) -> None:
        body = json.dumps(value).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if not self._local_only():
            return
        if self.path.startswith("/status"):
            serial = resolve_serial()
            running = bool(serial) and capturecam_running(serial)
            self._json({
                "ok": True, "adb": bool(serial), "serial": serial,
                "capturecam_running": running,
                "viewers": BROADCAST.viewer_count(), "streaming": BROADCAST.streaming,
                "screen": list(screen_size(serial)) if serial else None,
                "adb_endpoint": _reported_endpoint(),
            })
        elif self.path.startswith("/snapshot.png"):
            serial = resolve_serial()
            png = adb("exec-out", "screencap", "-p", serial=serial, timeout=12, binary=True) if serial else None
            if not png or not png.startswith(b"\x89PNG"):
                self._json({"ok": False, "error": "no screenshot"}, 503)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(png)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(png)
        elif self.path.startswith("/stream"):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            q = BROADCAST.subscribe()
            try:
                while True:
                    try:
                        self._chunk(q.get(timeout=2.0))
                    except queue.Empty:
                        self._chunk(struct.pack(">BI", 3, 0))
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                BROADCAST.unsubscribe(q)
        else:
            self.send_error(404)

    def do_POST(self):  # noqa: N802
        if not self._local_only():
            return
        if not self.path.startswith("/input"):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(min(length, 4096)) or b"{}")
            ok, message = inject(payload)
        except (ValueError, OSError) as exc:
            ok, message = False, str(exc)
        self._json({"ok": ok, "message": message}, 200 if ok else 400)


def main() -> None:
    threading.Thread(target=producer_loop, daemon=True, name="producer").start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.daemon_threads = True
    _log(f"tablet feed listening on 127.0.0.1:{PORT} adb={ADB}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
