package com.mdmesh.policy.devicesettings

import com.mdmesh.policy.wifi.DpmHandle

object BrightnessLevelPolicyFactory {
    fun create(handle: DpmHandle): BrightnessLevelPolicy? =
        listOf(BrightnessLevelSettingsPolicy(handle)).firstOrNull { it.isSupported() }
}
