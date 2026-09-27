#!/usr/bin/env python3
"""appop-guardian.py -- keeps WRITE_SETTINGS granted on every connected agent device.

Why this exists
----------------
`android.permission.WRITE_SETTINGS` (needed for AutoRotationSettingsPolicy /
Settings.System.ACCELEROMETER_ROTATION) is an AppOps-gated special permission with no
DevicePolicyManager API to grant it -- confirmed against AOSP master. It CAN be granted
once via `adb shell appops set <pkg> WRITE_SETTINGS allow`, but Android's own
PermissionPolicyService re-syncs app-op state on every package add/update event
(services/core/java/com/android/server/policy/PermissionPolicyService.java,
onPackageChanged -> resetAppOpPermissionsIfNotRequestedForUid), which silently reverts
the grant back to `ignore` -- reproduced twice on real hardware, including a build with
zero manifest/code changes. There is no in-app or Device-Owner fix for this; it is how
the OS handles this specific permission across app updates, full stop.

This script is the operational answer: run it on any always-on machine with the fleet's
kiosk tablets plugged in over USB (a spare PC, or a small Raspberry Pi at the shop). It
polls every connected device, and the instant it sees the agent's versionCode change (a
silent self-update just landed) or a brand-new device serial appear (freshly
provisioned), it re-applies the grant within one poll interval -- no person has to
remember to run `adb shell appops set` by hand after every fleet release.

Usage
-----
    python appop-guardian.py                    # default: poll every 15s, both package flavors
    python appop-guardian.py --interval 30
    python appop-guardian.py --package com.mdmesh.agent   # GMS flavor only
    python appop-guardian.py --once              # single pass, then exit (good for cron/Task Scheduler)

Requires: Python 3.7+, `adb` on PATH, USB debugging already enabled + authorized on
every target device (this script grants the appop; it does not bootstrap ADB access
itself -- see provision-aosp-device.ps1 for that one-time step).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_PACKAGES = ("com.mdmesh.agent", "com.mdmesh.agent.cn")
STATE_FILE = Path(__file__).with_name(".appop-guardian-state.json")
APPOP = "WRITE_SETTINGS"

# `adb.exe` is a console-subsystem app; launched under a windowless parent (pythonw, or
# any Task Scheduler action) each subprocess.run() would otherwise pop a fresh flashing
# console window per call -- several calls happen every poll. CREATE_NO_WINDOW suppresses
# that. Windows-only flag; no-op (0) elsewhere so this stays portable to a Pi/Linux box.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def adb(*args: str, serial: str | None = None, timeout: int = 15) -> subprocess.CompletedProcess:
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW)


def list_devices() -> list[str]:
    """Serials currently reporting 'device' (authorized, ready) state."""
    result = adb("devices")
    serials = []
    for line in result.stdout.splitlines()[1:]:
        line = line.strip()
        if not line or "\t" not in line and " " not in line:
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serials.append(parts[0])
    return serials


def get_version_code(serial: str, package: str) -> int | None:
    result = adb("shell", "dumpsys", "package", package, serial=serial)
    if result.returncode != 0:
        return None
    m = re.search(r"versionCode=(\d+)", result.stdout)
    return int(m.group(1)) if m else None


def get_appop_mode(serial: str, package: str) -> str | None:
    result = adb("shell", "dumpsys", "appops", "--package", package, serial=serial)
    m = re.search(rf"{APPOP}\s*\(([a-z]+)\)", result.stdout)
    return m.group(1) if m else None


def grant_write_settings(serial: str, package: str) -> bool:
    result = adb("shell", "appops", "set", package, APPOP, "allow", serial=serial)
    if result.returncode != 0:
        log(f"  ! appops set failed on {serial} ({package}): {result.stderr.strip() or result.stdout.strip()}")
        return False
    mode = get_appop_mode(serial, package)
    ok = mode == "allow"
    log(f"  {'OK' if ok else '!!'} {package} on {serial}: WRITE_SETTINGS now '{mode}'")
    return ok


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except OSError as e:
        log(f"  ! could not persist state file: {e}")


def poll_once(packages: tuple[str, ...], state: dict) -> dict:
    serials = list_devices()
    if not serials:
        log("no authorized devices connected")
        return state

    for serial in serials:
        device_state = state.setdefault(serial, {})
        for package in packages:
            version = get_version_code(serial, package)
            if version is None:
                continue  # this package flavor isn't installed on this device

            last_seen = device_state.get(package, {}).get("versionCode")
            mode = get_appop_mode(serial, package)
            is_new_device = last_seen is None
            version_changed = last_seen is not None and last_seen != version
            needs_grant = mode != "allow"

            if is_new_device:
                log(f"{serial}: first sighting of {package} (versionCode={version}), mode={mode}")
            elif version_changed:
                log(f"{serial}: {package} updated {last_seen} -> {version}, mode={mode}")

            if needs_grant:
                grant_write_settings(serial, package)
                mode = get_appop_mode(serial, package)

            device_state[package] = {"versionCode": version, "mode": mode, "checkedAt": time.time()}

    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interval", type=int, default=15, help="seconds between polls (default: 15)")
    parser.add_argument(
        "--package", action="append", dest="packages",
        help="package to watch (repeatable). Default: both com.mdmesh.agent and com.mdmesh.agent.cn",
    )
    parser.add_argument("--once", action="store_true", help="poll a single time, then exit (for cron/Task Scheduler)")
    args = parser.parse_args()

    packages = tuple(args.packages) if args.packages else DEFAULT_PACKAGES

    try:
        adb("version")
    except (FileNotFoundError, OSError):
        log("adb not found on PATH -- install Android platform-tools first")
        return 1

    log(f"appop-guardian starting -- watching {packages}, interval={args.interval}s")
    state = load_state()

    try:
        while True:
            state = poll_once(packages, state)
            save_state(state)
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        log("stopped by user")

    return 0


if __name__ == "__main__":
    sys.exit(main())
