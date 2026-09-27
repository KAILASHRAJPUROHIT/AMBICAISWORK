package com.mdmesh.policy.devicesettings

import com.mdmesh.policy.wifi.DpmHandle

/** Selects the [AutoRotationPolicy] strategy. The lone candidate self-gates on the
 * WRITE_SETTINGS appop being held; returns `null` (capability not advertised) otherwise. */
object AutoRotationPolicyFactory {
    fun create(handle: DpmHandle): AutoRotationPolicy? =
        listOf(AutoRotationSettingsPolicy(handle)).firstOrNull { it.isSupported() }
}
