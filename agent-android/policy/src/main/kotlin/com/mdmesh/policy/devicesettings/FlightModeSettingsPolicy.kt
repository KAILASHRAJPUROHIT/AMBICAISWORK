package com.mdmesh.policy.devicesettings

import android.os.Build
import android.provider.Settings
import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.wifi.DpmHandle

/**
 * `DevicePolicyManager.setGlobalSetting(AIRPLANE_MODE_ON)` strategy.
 *
 * API 28 (P) gate: this is a real platform floor for airplane mode specifically (unlike the
 * `enable_freeform_support` key `LockTaskKioskController` writes via the same method on
 * the same API surface but a different key with its own history) -- an enrolled device on
 * Android 7/8 correctly reports `flightMode` as unsupported rather than silently no-op'ing.
 * No WRITE_SETTINGS appop needed: this goes through Device Owner's own DPM grant, not a
 * plain `Settings.Global` write, so it needs nothing done at provisioning time.
 */
internal class FlightModeSettingsPolicy(
    private val handle: DpmHandle,
) : FlightModePolicy {

    override val capabilityKey: String = FlightModePolicy.CAPABILITY_KEY

    override fun isSupported(): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.P &&
            handle.dpm.isDeviceOwnerApp(handle.admin.packageName)

    override fun setEnabled(enabled: Boolean): PolicyOutcome = runCatching {
        handle.dpm.setGlobalSetting(
            handle.admin,
            Settings.Global.AIRPLANE_MODE_ON,
            if (enabled) "1" else "0",
        )
        PolicyOutcome.Applied
    }.getOrElse { PolicyOutcome.Failed(it.message ?: "flightMode setEnabled failed") }

    // Readable regardless of write permission -- Settings.Global.getInt needs no appop.
    override fun isEnabled(): Boolean? = runCatching {
        Settings.Global.getInt(handle.context.contentResolver, Settings.Global.AIRPLANE_MODE_ON) == 1
    }.getOrNull()
}
