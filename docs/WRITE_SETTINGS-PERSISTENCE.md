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

## Going USB-free: `tools/wireless-adb-reconnect.py`

Since this fleet's devices never leave the shop, a one-time *manual* wireless-debugging
pairing per device (Settings > Developer options > Wireless debugging -- a real human
tapping the toggle, not a programmatic write) is a different code path from the
`adb_wifi_enabled` programmatic-write attempts that got reverted earlier in this
investigation, and is exactly the mechanism every consumer phone relies on daily. This
fleet already has live proof it persists: one tablet has stayed reachable over wireless
ADB (via mDNS) across this entire investigation, through however many reboots, with zero
programmatic intervention.

The one thing that doesn't survive on its own is the *connection* -- modern wireless
debugging advertises a new ephemeral port per session via mDNS, so `adb connect` needs
re-running after every reboot. `tools/wireless-adb-reconnect.py` watches for the mDNS
advertisement and reconnects automatically the moment a device reappears. Run it
alongside `appop-guardian.py` and, once every device has done the one-time pairing in
the script's own docstring, the whole fleet needs zero USB and zero manual touch from
then on.
