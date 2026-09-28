package com.mdmesh.policy.devicesettings

import android.os.Build
import android.provider.Settings
import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.wifi.DpmHandle
import kotlin.math.roundToInt

/**
 * `DevicePolicyManager.setSystemSetting(SCREEN_BRIGHTNESS)` strategy (raw range 0-255,
 * exposed as 0-100%). See [AutoBrightnessSettingsPolicy]'s doc comment for why this goes
 * through `setSystemSetting` (confirmed on `SYSTEM_SETTINGS_ALLOWLIST`) rather than a plain
 * `Settings.System` write -- no WRITE_SETTINGS appop, no per-device provisioning step.
 */
internal class BrightnessLevelSettingsPolicy(
    private val handle: DpmHandle,
) : BrightnessLevelPolicy {

    override val capabilityKey: String = BrightnessLevelPolicy.CAPABILITY_KEY

    override fun isSupported(): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.P &&
            handle.dpm.isDeviceOwnerApp(handle.admin.packageName)

    override fun setLevel(percent: Int): PolicyOutcome {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) return PolicyOutcome.Unsupported
        return runCatching {
        val clamped = percent.coerceIn(0, 100)
        val raw = (clamped * 255 / 100.0).roundToInt().coerceIn(1, 255) // 0 can leave the panel unreadable
        handle.dpm.setSystemSetting(handle.admin, Settings.System.SCREEN_BRIGHTNESS, raw.toString())
        PolicyOutcome.Applied
        }.getOrElse { PolicyOutcome.Failed(it.message ?: "brightnessLevel setLevel failed") }
    }

    override fun getLevel(): Int? = runCatching {
        val raw = Settings.System.getInt(handle.context.contentResolver, Settings.System.SCREEN_BRIGHTNESS)
        (raw * 100 / 255.0).roundToInt().coerceIn(0, 100)
    }.getOrNull()
}
