package com.mdmesh.policy.devicesettings

import android.provider.Settings
import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.wifi.DpmHandle
import kotlin.math.roundToInt

/**
 * `Settings.System.SCREEN_BRIGHTNESS` strategy (raw range 0-255, exposed as 0-100%). Same
 * WRITE_SETTINGS gate and provisioning story as [AutoRotationSettingsPolicy].
 */
internal class BrightnessLevelSettingsPolicy(
    private val handle: DpmHandle,
) : BrightnessLevelPolicy {

    override val capabilityKey: String = BrightnessLevelPolicy.CAPABILITY_KEY

    override fun isSupported(): Boolean =
        handle.dpm.isDeviceOwnerApp(handle.admin.packageName) &&
            Settings.System.canWrite(handle.context)

    override fun setLevel(percent: Int): PolicyOutcome = runCatching {
        val clamped = percent.coerceIn(0, 100)
        val raw = (clamped * 255 / 100.0).roundToInt().coerceIn(1, 255) // 0 can leave the panel unreadable
        Settings.System.putInt(handle.context.contentResolver, Settings.System.SCREEN_BRIGHTNESS, raw)
        PolicyOutcome.Applied
    }.getOrElse { PolicyOutcome.Failed(it.message ?: "brightnessLevel setLevel failed") }

    override fun getLevel(): Int? = runCatching {
        val raw = Settings.System.getInt(handle.context.contentResolver, Settings.System.SCREEN_BRIGHTNESS)
        (raw * 100 / 255.0).roundToInt().coerceIn(0, 100)
    }.getOrNull()
}
