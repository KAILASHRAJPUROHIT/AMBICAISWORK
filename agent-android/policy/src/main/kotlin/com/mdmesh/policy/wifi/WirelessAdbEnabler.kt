package com.mdmesh.policy.wifi

import android.os.Build
import android.provider.Settings

/**
 * Shared logic behind `device.enableWirelessAdb` (see
 * `DeviceEnableWirelessAdbHandler` in :core) and [com.mdmesh.agent.service.BootReceiver]'s
 * post-boot re-enable attempt. One function so both call sites can't drift.
 *
 * `ADB_WIFI_ENABLED` and `ADB_ENABLED` are both confirmed on
 * `DevicePolicyManagerService.GLOBAL_SETTINGS_ALLOWLIST` (AOSP master) -- Device Owner can
 * flip them via `setGlobalSetting` and it throws nothing.
 *
 * Real, tested limitation (2026-09-27, real hardware): on this fleet's Xiaomi/HyperOS build,
 * enabling wireless debugging while the device is already running (via the remote
 * `device.enableWirelessAdb` command, mid-session) sticks correctly. Whether the SAME
 * privileged write, run from [com.mdmesh.agent.service.BootReceiver] at
 * `ACTION_BOOT_COMPLETED` -- i.e. before Xiaomi's own boot-time developer-options reset runs,
 * rather than well after boot -- survives is the open, unverified question this call site
 * exists to test. Do not assume it works without checking a real reboot; do not remove this
 * doc note until that's actually confirmed either way.
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
