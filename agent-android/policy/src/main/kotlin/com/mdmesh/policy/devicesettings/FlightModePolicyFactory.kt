package com.mdmesh.policy.devicesettings

import com.mdmesh.policy.wifi.DpmHandle

object FlightModePolicyFactory {
    fun create(handle: DpmHandle): FlightModePolicy? =
        listOf(FlightModeSettingsPolicy(handle)).firstOrNull { it.isSupported() }
}
