package com.mdmesh.policy.devicesettings

import android.provider.Settings
import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.wifi.DpmHandle

/**
 * `Settings.System.SCREEN_BRIGHTNESS_MODE` strategy. Same WRITE_SETTINGS gate and
 * provisioning story as [AutoRotationSettingsPolicy] -- see that class's doc comment.
 */
internal class AutoBrightnessSettingsPolicy(
    private val handle: DpmHandle,
) : AutoBrightnessPolicy {

    override val capabilityKey: String = AutoBrightnessPolicy.CAPABILITY_KEY

    override fun isSupported(): Boolean =
        handle.dpm.isDeviceOwnerApp(handle.admin.packageName) &&
            Settings.System.canWrite(handle.context)

    override fun setEnabled(enabled: Boolean): PolicyOutcome = runCatching {
        Settings.System.putInt(
            handle.context.contentResolver,
            Settings.System.SCREEN_BRIGHTNESS_MODE,
            if (enabled) Settings.System.SCREEN_BRIGHTNESS_MODE_AUTOMATIC
            else Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL,
        )
        PolicyOutcome.Applied
    }.getOrElse { PolicyOutcome.Failed(it.message ?: "autoBrightness setEnabled failed") }

    override fun isEnabled(): Boolean? = runCatching {
        Settings.System.getInt(handle.context.contentResolver, Settings.System.SCREEN_BRIGHTNESS_MODE) ==
            Settings.System.SCREEN_BRIGHTNESS_MODE_AUTOMATIC
    }.getOrNull()
}
