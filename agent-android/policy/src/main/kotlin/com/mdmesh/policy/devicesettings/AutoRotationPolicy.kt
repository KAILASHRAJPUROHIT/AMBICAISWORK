package com.mdmesh.policy.devicesettings

import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.ReadableTogglePolicy

/**
 * Screen auto-rotation control.
 *
 * `setEnabled(true)` unlocks rotation (`Settings.System.ACCELEROMETER_ROTATION = 1`);
 * `setEnabled(false)` locks it to the current orientation (`= 0`). Backed by a plain
 * `Settings.System` write, which requires the WRITE_SETTINGS appop -- see
 * [AutoRotationSettingsPolicy]'s own doc comment for why that is granted once via
 * `adb shell appops set` at provisioning rather than the normal
 * `Settings.ACTION_MANAGE_WRITE_SETTINGS` consent screen. Selected by
 * [AutoRotationPolicyFactory].
 */
interface AutoRotationPolicy : ReadableTogglePolicy {

    override fun setEnabled(enabled: Boolean): PolicyOutcome
    override fun isEnabled(): Boolean?

    companion object {
        const val CAPABILITY_KEY = "autoRotation"
    }
}
