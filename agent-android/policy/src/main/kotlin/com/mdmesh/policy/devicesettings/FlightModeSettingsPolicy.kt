package com.mdmesh.policy.devicesettings

import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.wifi.DpmHandle

/**
 * RETRACTED 2026-09-27, before ever shipping to a real device.
 *
 * The first version of this file called `DevicePolicyManager.setGlobalSetting(admin,
 * Settings.Global.AIRPLANE_MODE_ON, ...)`, on the strength of secondary sources (a vendor blog,
 * a generic API-wrapper doc) that described it as Device Owner's documented path for airplane
 * mode. Checked afterward against the actual enforcing source --
 * `DevicePolicyManagerService.GLOBAL_SETTINGS_ALLOWLIST` in AOSP master -- and `AIRPLANE_MODE_ON`
 * is NOT in it. The real list is: `ADB_ENABLED`, `ADB_WIFI_ENABLED`, `AUTO_TIME`,
 * `AUTO_TIME_ZONE`, `DATA_ROAMING`, `USB_MASS_STORAGE_ENABLED`, `WIFI_SLEEP_POLICY`,
 * `STAY_ON_WHILE_PLUGGED_IN`, `WIFI_DEVICE_OWNER_CONFIGS_LOCKDOWN`, `PRIVATE_DNS_MODE`,
 * `PRIVATE_DNS_SPECIFIER`. Calling `setGlobalSetting` with a key outside this list throws
 * `SecurityException` at the framework level -- this would have failed on first real use, not
 * degraded gracefully.
 *
 * A plain `Settings.Global.putInt(AIRPLANE_MODE_ON, ...)` doesn't work either: it only changes
 * the stored value. Actually toggling the radios needs a follow-up
 * `ACTION_AIRPLANE_MODE_CHANGED` broadcast, which is protected -- no non-system app, Device
 * Owner included, may send it on modern Android.
 *
 * No known general, Device-Owner-reachable, non-root API achieves real airplane mode on stock
 * Android. `isSupported()` returns false unconditionally so the capability is never advertised
 * and the "Flight mode" row simply does not appear -- exactly the existing "absence == not
 * advertised" contract, not a special case. If this is needed later: the honest paths are (a) an
 * OEM-specific enterprise API for this fleet's specific hardware, if one exists, or (b) toggling
 * Wi-Fi and Bluetooth off individually as a practical substitute -- NOT reusable as-is today:
 * `ModernWifiPolicy.setEnabled()`'s own doc comment says its radio toggle isn't wired yet either
 * (only the config-lock restriction is real), so that would need finishing first, not just
 * composing.
 */
internal class FlightModeSettingsPolicy(
    @Suppress("UNUSED_PARAMETER") private val handle: DpmHandle,
) : FlightModePolicy {

    override val capabilityKey: String = FlightModePolicy.CAPABILITY_KEY

    override fun isSupported(): Boolean = false

    override fun setEnabled(enabled: Boolean): PolicyOutcome = PolicyOutcome.Unsupported

    override fun isEnabled(): Boolean? = null
}
