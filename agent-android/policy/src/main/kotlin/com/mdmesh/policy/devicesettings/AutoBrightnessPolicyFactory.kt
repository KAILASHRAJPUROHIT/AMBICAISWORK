package com.mdmesh.policy.devicesettings

import com.mdmesh.policy.wifi.DpmHandle

object AutoBrightnessPolicyFactory {
    fun create(handle: DpmHandle): AutoBrightnessPolicy? =
        listOf(AutoBrightnessSettingsPolicy(handle)).firstOrNull { it.isSupported() }
}
