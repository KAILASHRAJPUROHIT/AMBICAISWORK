package com.mdmesh.policy.devicesettings

import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.PolicyStrategy

/**
 * Absolute screen brightness, as a 0-100 percentage (Android's own
 * `Settings.System.SCREEN_BRIGHTNESS` range is 0-255; percentage is the friendlier unit
 * for a UI slider and for a future `policy.apply`-style remote command).
 *
 * Not a [com.mdmesh.policy.TogglePolicy] -- a level isn't boolean, so it gets its own tiny
 * [PolicyStrategy], deliberately outside [com.mdmesh.policy.CapabilityRegistry.togglePolicies]'s
 * `Map<String, TogglePolicy>` (that map's value type is boolean-shaped; forcing this into it
 * would need a `TogglePolicy.setEnabled` that lies about what one call means). Exposed
 * separately via `CapabilityRegistry.brightnessLevelPolicy()`.
 *
 * Setting a level while [AutoBrightnessPolicy] is on has no lasting visible effect -- see
 * that policy's own doc comment -- callers driving a UI slider should read
 * [AutoBrightnessPolicy.isEnabled] first and prompt to turn adaptive brightness off, the same
 * way Android's own quick-settings brightness slider behaves.
 */
interface BrightnessLevelPolicy : PolicyStrategy {
    fun setLevel(percent: Int): PolicyOutcome
    fun getLevel(): Int?

    companion object {
        const val CAPABILITY_KEY = "brightnessLevel"
    }
}
