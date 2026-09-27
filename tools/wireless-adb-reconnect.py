#!/usr/bin/env python3
"""wireless-adb-reconnect.py -- keeps `adb` connected to every paired wireless-debug
device on the LAN, automatically, forever -- no USB tether needed after the one-time
setup below.

Why this is different from the earlier "wireless ADB" attempts this session
-----------------------------------------------------------------------------
Programmatically flipping `adb_wifi_enabled` (via `adb shell settings put` or even
`DevicePolicyManager.setGlobalSetting`) gets silently reverted by this hardware -- that
was confirmed and is a dead end (see docs/WRITE_SETTINGS-PERSISTENCE.md for the same
class of problem). But a REAL person manually enabling Developer Options > Wireless
debugging and pairing once is a completely different code path -- it's the same
mechanism every Pixel/Samsung/Xiaomi phone owner uses daily, and it survives reboots
normally. This fleet already has live proof of that: one tablet has been reachable over
wireless ADB (via mDNS) for this entire session, across however many reboots, with zero
programmatic intervention.

The one thing that does NOT survive a reboot on its own is the *connection* --
`adb connect <ip>:<port>` needs re-running every time the device reboots or the
ephemeral TLS port changes, since modern wireless debugging (API 30+) advertises a new
random port per session via mDNS rather than a fixed one. That's the actual gap this
script closes: it watches for the mDNS advertisement and reconnects automatically the
moment a device reappears, so nobody has to notice or run `adb connect` by hand.

One-time setup PER DEVICE (do this once, physically, since these devices never leave
the shop):
    1. Settings > About tablet > tap "Build number" 7x to unlock Developer Options.
    2. Settings > Additional settings > Developer options > enable "Wireless debugging".
    3. Tap "Pair device with pairing code", note the IP:port + 6-digit code shown.
    4. On this machine:  adb pair <ip>:<pairing-port>   (enter the 6-digit code)
    5. Done -- from then on this script (or a plain `adb connect`) reaches it without
       ever touching that device's screen again, reboot or no reboot.

Usage
-----
    python wireless-adb-reconnect.py                 # loop forever, poll every 10s
    python wireless-adb-reconnect.py --interval 30
    python wireless-adb-reconnect.py --once           # single pass, then exit

Pairs naturally with appop-guardian.py: once a device is connected here, it shows up in
plain `adb devices`, which is all appop-guardian.py needs -- run both, no USB required
for any device that's completed the one-time pairing above.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time

MDNS_CONNECT_SERVICE = "_adb-tls-connect._tcp"

# See appop-guardian.py's comment on this same constant: suppresses the flashing console
# window adb.exe would otherwise pop per call when run under a windowless (pythonw) parent.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def adb(*args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(["adb", *args], capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW)


def discovered_endpoints() -> dict[str, str]:
    """{mdns_name: 'ip:port'} for every advertised wireless-debug endpoint on the LAN."""
    result = adb("mdns", "services")
    endpoints = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] == MDNS_CONNECT_SERVICE:
            name, _, address = parts[0], parts[1], parts[2]
            endpoints[name] = address
    return endpoints


def connected_addresses() -> set[str]:
    """ip:port / serial strings adb currently reports as 'device' (already connected)."""
    result = adb("devices")
    addrs = set()
    for line in result.stdout.splitlines()[1:]:
        line = line.strip()
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            addrs.add(parts[0])
    return addrs


def poll_once(known_names: dict[str, str]) -> dict[str, str]:
    endpoints = discovered_endpoints()
    live = connected_addresses()

    for name, address in endpoints.items():
        already_connected = address in live
        is_new_name = name not in known_names
        address_changed = not is_new_name and known_names[name] != address

        if is_new_name:
            log(f"discovered {name} at {address}")
        elif address_changed:
            log(f"{name} reappeared at a new address: {known_names[name]} -> {address} (reboot or reconnect)")

        if not already_connected:
            result = adb("connect", address)
            ok = "connected" in result.stdout.lower()
            log(f"  {'OK' if ok else '!!'} adb connect {address}: {result.stdout.strip() or result.stderr.strip()}")

        known_names[name] = address

    # Nothing to do for names we've seen before whose address hasn't changed and are
    # already connected -- that's the steady state, and it should be silent.
    return known_names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interval", type=int, default=10, help="seconds between polls (default: 10)")
    parser.add_argument("--once", action="store_true", help="poll a single time, then exit")
    args = parser.parse_args()

    try:
        adb("version")
    except (FileNotFoundError, OSError):
        log("adb not found on PATH -- install Android platform-tools first")
        return 1

    check = adb("mdns", "check")
    if "version" not in check.stdout.lower():
        log("this adb build has no mDNS support -- update platform-tools (needs a reasonably recent adb)")
        return 1

    log(f"wireless-adb-reconnect starting -- interval={args.interval}s")
    known: dict[str, str] = {}

    try:
        while True:
            known = poll_once(known)
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        log("stopped by user")

    return 0


if __name__ == "__main__":
    sys.exit(main())
