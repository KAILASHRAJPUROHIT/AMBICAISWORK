# Known device identifiers (shop tablet name -> adb/model identity)

Reference for reading `appop-guardian.py` / `wireless-adb-reconnect.py` log output --
`adb devices` shows serials/addresses, not shop names. Add to this as devices get
wireless-debugging paired.

| Shop name | ADB serial | Model | `product` prop | Android ID | Notes |
|---|---|---|---|---|---|
| TAB PRO | `cd28fb7746c2` | `2509BRP2DI` | `organ_in` | `1f1548790ddf2361` | Wireless debugging paired; confirmed 2026-09-27. mDNS name `adb-cd28fb7746c2-eXqHAf`. |
| TAB2 | `t4e6vcsopbzxu4of` | `2505DRP06I` | `koto_in` | -- | Wireless debugging paired 2026-09-27. mDNS name `adb-t4e6vcsopbzxu4of-vpZtOe`. |
| TAB3 | `mnjnz99hs4pfo745` | `2505DRP06I` | `koto_in` | `343a945276ddff89` | Wireless debugging paired 2026-09-28. mDNS name `adb-mnjnz99hs4pfo745-gxWWw9`. |
| TAB1 | `xgqwpzwody6d5ltc` | `2505DRP06I` | `koto_in` | `f7626b38e7ec166c` | Wireless debugging paired 2026-09-28. mDNS name `adb-xgqwpzwody6d5ltc-aXvOT2`. |
| REDMI14R | -- | `2411DRN47C` | -- | -- | China HyperOS, Device Owner signed with the laptop DEBUG key: only `tools/update-14r.py` (debug-signed CN APK, `adb install -r`) can update it; never the release APK. See `docs/14R-UPDATES.md`. Not yet paired for wireless adb (2026-10-04). |

USB serials (`t4e6vcsopbzxu4of`-style) and wireless addresses (`192.168.0.12:PORT`) are
stable identifiers per-device via `ro.serialno`, but the wireless *port* is ephemeral
per session -- match by serial/Android ID, not by the current `ip:port` in an `adb
devices` listing.
