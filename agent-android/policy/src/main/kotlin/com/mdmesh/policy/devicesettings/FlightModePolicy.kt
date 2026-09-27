package com.mdmesh.policy.devicesettings

import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.ReadableTogglePolicy

/**
 * Airplane/flight mode control.
 *
 * Deliberately NOT a plain `Settings.Global.putInt` (which only changes the *stored value*
 * -- actually toggling the radios needs a follow-up `ACTION_AIRPLANE_MODE_CHANGED`
 * broadcast, and that is a protected broadcast no non-system app, Device Owner included, may
 * send on modern Android). `DevicePolicyManager.setGlobalSetting` is the platform's own
 * answer to exactly that gap: Device Owner's documented, Android-9+-only path for airplane
 * mode specifically, which the OS applies for real. See [FlightModeSettingsPolicy].
 */
interface FlightModePolicy : ReadableTogglePolicy {

    override fun setEnabled(enabled: Boolean): PolicyOutcome
    override fun isEnabled(): Boolean?

    companion object {
        const val CAPABILITY_KEY = "flightMode"
    }
}
