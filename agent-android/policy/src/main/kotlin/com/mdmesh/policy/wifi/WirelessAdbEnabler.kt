package com.mdmesh.policy.wifi

import android.os.Build
import android.provider.Settings

/**
 * Shared logic behind `device.enableWirelessAdb` (`DeviceEnableWirelessAdbHandler` in :core)
 * and the app's `WirelessAdbKeeper`. One function so the call sites can't drift.
 *
 * `ADB_WIFI_ENABLED` and `ADB_ENABLED` are both on
 * `DevicePolicyManagerService.GLOBAL_SETTINGS_ALLOWLIST` (AOSP master), so Device Owner can
 * write them via `setGlobalSetting` without an exception.
 *
 * The write only *sticks* if the device is on Wi-Fi and that network is already trusted for
 * wireless debugging. AOSP's `AdbDebuggingManager.verifyWifiNetwork` resets it to 0 otherwise.
 * A network becomes trusted the first time someone enables wireless debugging on it by hand and
 * accepts "always allow". That is why a push to an unpaired device read back 0 on 2026-09-27,
 * while a push to paired TAB PRO on 2026-09-28 worked.
 */
object WirelessAdbEnabler {

    fun tryEnable(handle: DpmHandle): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return false
        if (!handle.dpm.isDeviceOwnerApp(handle.admin.packageName)) return false
        return runCatching {
            handle.dpm.setGlobalSetting(handle.admin, Settings.Global.ADB_ENABLED, "1")
            // Settings.Global.ADB_WIFI_ENABLED isn't a public SDK constant (added API 30, hidden) --
            // the literal key is what DevicePolicyManagerService's allow-list and Settings.Global
            // itself both key on, confirmed against AOSP master alongside ADB_ENABLED.
            handle.dpm.setGlobalSetting(handle.admin, "adb_wifi_enabled", "1")
            true
        }.getOrDefault(false)
    }
}
