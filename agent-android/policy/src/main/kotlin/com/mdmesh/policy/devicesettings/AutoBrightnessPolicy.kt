package com.mdmesh.policy.devicesettings

import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.ReadableTogglePolicy

/**
 * Adaptive-brightness control: `setEnabled(true)` switches
 * `Settings.System.SCREEN_BRIGHTNESS_MODE` to automatic; `false` switches it to manual
 * (which is also the precondition for [BrightnessLevelPolicy].setLevel to have any visible
 * effect -- while automatic mode is on, the OS's own brightness curve overrides a plain
 * `SCREEN_BRIGHTNESS` write on the next light-sensor tick). Same WRITE_SETTINGS gate as
 * [AutoRotationPolicy]. Selected by [AutoBrightnessPolicyFactory].
 */
interface AutoBrightnessPolicy : ReadableTogglePolicy {

    override fun setEnabled(enabled: Boolean): PolicyOutcome
    override fun isEnabled(): Boolean?

    companion object {
        const val CAPABILITY_KEY = "autoBrightness"
    }
}
