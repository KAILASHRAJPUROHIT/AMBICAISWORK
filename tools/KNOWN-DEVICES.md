# Known device identifiers (shop tablet name -> adb/model identity)

Reference for reading `appop-guardian.py` / `wireless-adb-reconnect.py` log output --
`adb devices` shows serials/addresses, not shop names. Add to this as devices get
wireless-debugging paired.

| Shop name | ADB serial | Model | `product` prop | Android ID | Notes |
|---|---|---|---|---|---|
| TAB PRO | `cd28fb7746c2` | `2509BRP2DI` | `organ_in` | `1f1548790ddf2361` | Wireless debugging paired; confirmed 2026-09-27. mDNS name `adb-cd28fb7746c2-eXqHAf`. |
| TAB2 | `t4e6vcsopbzxu4of` | `2505DRP06I` | `koto_in` | -- | USB only as of 2026-09-27; not yet wireless-paired. |

USB serials (`t4e6vcsopbzxu4of`-style) and wireless addresses (`192.168.0.12:PORT`) are
stable identifiers per-device via `ro.serialno`, but the wireless *port* is ephemeral
per session -- match by serial/Android ID, not by the current `ip:port` in an `adb
devices` listing.
