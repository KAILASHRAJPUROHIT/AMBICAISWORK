package com.mdmesh.policy.devicesettings

import android.os.Build
import android.provider.Settings
import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.wifi.DpmHandle

/**
 * `DevicePolicyManager.setSystemSetting(SCREEN_BRIGHTNESS_MODE)` strategy.
 *
 * Revised 2026-09-27: the first version of this file wrote `Settings.System` directly and
 * required the WRITE_SETTINGS appop (see [AutoRotationSettingsPolicy] for why that needs a
 * one-time `adb` touch per device). Checked against the actual enforcing source
 * (`DevicePolicyManagerService.SYSTEM_SETTINGS_ALLOWLIST`, AOSP master) rather than the javadoc
 * prose: `SCREEN_BRIGHTNESS_MODE` (and `SCREEN_BRIGHTNESS`, `SCREEN_OFF_TIMEOUT`) ARE on that
 * allow-list, so Device Owner can write them through `setSystemSetting` directly -- no appop, no
 * per-device provisioning step, works immediately on every already-enrolled device including
 * ones enrolled via QR/GMS with no ADB moment ever available. `ACCELEROMETER_ROTATION` is NOT on
 * this list (confirmed the same way), which is why [AutoRotationSettingsPolicy] still needs the
 * appop -- that gap is real, this one wasn't.
 *
 * The read path is unaffected: `Settings.System.getInt` needs no special permission for either
 * key, appop or not.
 */
internal class AutoBrightnessSettingsPolicy(
    private val handle: DpmHandle,
) : AutoBrightnessPolicy {

    override val capabilityKey: String = AutoBrightnessPolicy.CAPABILITY_KEY

    override fun isSupported(): Boolean =
        // setSystemSetting is API 24+ per its own javadoc, but (as LockTaskKioskController's own
        // doc comment notes for a different key on the same method) lint ties this overload to
        // API 28 -- gate explicitly rather than rely on minSdk alone.
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.P &&
            handle.dpm.isDeviceOwnerApp(handle.admin.packageName)

    override fun setEnabled(enabled: Boolean): PolicyOutcome {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) return PolicyOutcome.Unsupported
        return runCatching {
        handle.dpm.setSystemSetting(
            handle.admin,
            Settings.System.SCREEN_BRIGHTNESS_MODE,
            if (enabled) Settings.System.SCREEN_BRIGHTNESS_MODE_AUTOMATIC.toString()
            else Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL.toString(),
        )
        PolicyOutcome.Applied
        }.getOrElse { PolicyOutcome.Failed(it.message ?: "autoBrightness setEnabled failed") }
    }

    override fun isEnabled(): Boolean? = runCatching {
        Settings.System.getInt(handle.context.contentResolver, Settings.System.SCREEN_BRIGHTNESS_MODE) ==
            Settings.System.SCREEN_BRIGHTNESS_MODE_AUTOMATIC
    }.getOrNull()
}
