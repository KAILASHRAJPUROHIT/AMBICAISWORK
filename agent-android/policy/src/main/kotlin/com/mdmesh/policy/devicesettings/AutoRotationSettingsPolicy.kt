package com.mdmesh.policy.devicesettings

import android.provider.Settings
import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.wifi.DpmHandle

/**
 * `Settings.System.ACCELEROMETER_ROTATION` strategy.
 *
 * This key has no `DevicePolicyManager` allow-list entry ([setSystemSetting] does not
 * cover it) -- it is a plain `Settings.System` write, gated on the WRITE_SETTINGS appop
 * (`Settings.System.canWrite()`), same as any third-party rotation-lock app. The
 * difference here: that appop is granted ONCE, silently, via
 * `adb shell appops set <package> WRITE_SETTINGS allow` in
 * `tools/provision-aosp-device.ps1`, at the same moment Device Owner itself is assigned --
 * never through the `Settings.ACTION_MANAGE_WRITE_SETTINGS` consent screen, which would put
 * the kiosked end user one screen away from the real Settings app. [isSupported] reflects
 * that grant directly rather than assuming it: a device provisioned before this existed, or
 * enrolled through a path that skips the ADB step (GMS/QR provisioning has no ADB moment to
 * run it), correctly reports the capability as absent instead of failing silently.
 */
internal class AutoRotationSettingsPolicy(
    private val handle: DpmHandle,
) : AutoRotationPolicy {

    override val capabilityKey: String = AutoRotationPolicy.CAPABILITY_KEY

    override fun isSupported(): Boolean =
        handle.dpm.isDeviceOwnerApp(handle.admin.packageName) &&
            Settings.System.canWrite(handle.context)

    override fun setEnabled(enabled: Boolean): PolicyOutcome = runCatching {
        Settings.System.putInt(
            handle.context.contentResolver,
            Settings.System.ACCELEROMETER_ROTATION,
            if (enabled) 1 else 0,
        )
        PolicyOutcome.Applied
    }.getOrElse { PolicyOutcome.Failed(it.message ?: "autoRotation setEnabled failed") }

    override fun isEnabled(): Boolean? = runCatching {
        Settings.System.getInt(handle.context.contentResolver, Settings.System.ACCELEROMETER_ROTATION) == 1
    }.getOrNull()
}
