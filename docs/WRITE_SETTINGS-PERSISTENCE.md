# WRITE_SETTINGS doesn't survive agent updates -- why, and what to do about it

`AutoRotationSettingsPolicy` (the Quick Controls "Auto-rotate screen" toggle) needs the
`android.permission.WRITE_SETTINGS` AppOp granted via `adb shell appops set <pkg>
WRITE_SETTINGS allow`. This grant **does not survive the next agent update**, on any
hardware, not just this fleet's Xiaomi devices. This is fully investigated and closed
out -- don't re-litigate it without new information. Run `tools/appop-guardian.py`
instead of re-researching this.

## Root cause (confirmed against AOSP source, reproduced twice on real hardware)

Android's `PermissionPolicyService` re-syncs every app's special-access AppOps on every
package add/update event:
`onPackageChanged()` -> `synchronizeUidPermissionsAndAppOps()` /
`resetAppOpPermissionsIfNotRequestedForUid()`
(`services/core/java/com/android/server/policy/PermissionPolicyService.java`, AOSP
master). This is stock AOSP behavior, not an MIUI patch -- reproduced with a version
bump that changed zero manifest/code lines.

## Every other avenue was checked and closed, with evidence, not guesses

| Avenue | Result |
|---|---|
| `DevicePolicyManager` API to set/preserve the AppOp | Does not exist -- checked current AOSP master. `setSystemSetting()`/`setGlobalSetting()`'s allow-lists (brightness, screen timeout, ADB enable) don't cover this. |
| Android Role system (`DEVICE_POLICY_MANAGEMENT` / `RETAIL_DEMO` roles both grant `WRITE_SETTINGS` permanently per `roles.xml`) | Both require a component guarded by `android.permission.LAUNCH_DEVICE_MANAGER_SETUP`, which is `@hide` and `protectionLevel="signature|role"` -- unreachable for an app not signed with the platform key. Reproduced the exact on-device rejection (`RoleControllerServiceImpl: Package does not qualify ... missing RequiredComponent ... LAUNCH_DEVICE_MANAGER_SETUP`). |
| Mi OEMConfig (`com.xiaomi.oemconfig`) | Installed it and inspected the real `res/xml/app_restrictions.xml` + `classes.dex` directly. Exactly two keys exist: `DisableFactoryResetProtectionLock`, `DisableSystemUpdate`. Zero mentions of rotation/accelerometer/WRITE_SETTINGS anywhere in the APK. Not a partial answer -- a complete dead end. |
| `WRITE_SETTINGS`'s own protection level | `signature\|preinstalled\|appop\|pre23\|role` (AOSP `core/res/AndroidManifest.xml`). Permanent auto-grant only happens for a platform-signed app, a preinstalled/system-partition app, an app targeting API <23, or a holder of one of the two roles above. None available to a normal third-party-signed Device Owner app. |
| Android 16 (API 36) specifically | Checked for anything new. The one real API-36 AppOps change found (`AppOpService.kt`'s stricter `setUidMode`) only blocks ops backed by *dangerous/runtime* permissions (location, mic, etc.) -- confirmed via the exact source condition. `WRITE_SETTINGS` isn't in that category; unaffected either way. |

## What's left

1. **`tools/appop-guardian.py`** -- the operational fix. Run it on any always-on machine
   with the fleet's tablets on USB (or reachable over already-established wireless ADB).
   It polls every connected device, and the moment it sees the agent's versionCode
   change (a silent self-update just landed) or a new device serial appear, it
   re-applies the grant within one poll interval. This is what's actually deployed;
   don't rely on a one-time manual `appops set` ever again.
2. **Xiaomi's enterprise program** (`miui-enterprise-dev@xiaomi.com`) is the only
   remaining path to a true permanent fix -- their EnterpriseSDK (not OEMConfig, which
   is confirmed useless for this) may expose a privileged rotation API that doesn't need
   `WRITE_SETTINGS` at all. This requires an actual business/vendor relationship with
   Xiaomi; it's not something buildable from this codebase. Pursue it separately if
   wanted; it does not block shipping rotation today via the guardian script.

## Keeping every tablet reachable: wireless debugging

`appop-guardian.py` can only re-grant what it can reach, so every tablet has to stay reachable
over wireless ADB. Three pieces make that hold:

1. **One-time pairing per tablet** (by hand, since these tablets never leave the shop):
   Developer options > Wireless debugging > Pair device with pairing code, then
   `adb pair <ip>:<port> <code>` on the shop PC. Enabling wireless debugging by hand on the shop
   Wi-Fi also marks that network *trusted*, which step 2 depends on. `tools/KNOWN-DEVICES.md`
   lists which tabs are paired.

2. **`WirelessAdbKeeper` in the agent (v0.2.66+)** keeps the listener on. Android turns
   wireless debugging off on *every* Wi-Fi disconnect and on reboot. This is stock AOSP
   (`AdbDebuggingManager`: "Network disconnected. Disabling adbwifi."), not Xiaomi. It only
   honours an enable when the device is on Wi-Fi *and* the network is trusted
   (`verifyWifiNetwork`). The keeper watches `adb_wifi_enabled` and Wi-Fi availability, and
   re-enables it via Device Owner `setGlobalSetting` whenever it's off while on Wi-Fi (max 3
   tries per connection, so an untrusted network can't loop). Verified 2026-09-28 on TAB2:
   Wi-Fi off, then on, and the keeper re-enabled it on the first attempt about 3s after Wi-Fi
   returned, with no touch.

   An earlier "Xiaomi reverts it" theory (a remote enable on an *unpaired* device read back
   0) was wrong. That device's network simply wasn't trusted yet.

3. **The PC side** reconnects automatically. Recent adb auto-connects to paired devices it
   sees over mDNS (they show up as `<name>._adb-tls-connect._tcp`).
   `tools/wireless-adb-reconnect.py` is a fallback that dials the advertised address only
   when that transport is missing. The address `adb mdns services` shows can be stale after
   DHCP changes, so the script backs off instead of retrying every poll.

Both watchers run as Windows scheduled tasks ("MDM AppOp Guardian", "MDM Wireless ADB
Reconnect") and log to `tools/logs/`.
