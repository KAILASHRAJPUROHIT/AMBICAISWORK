package com.mdmesh.policy.antitamper

import com.mdmesh.policy.wifi.DpmHandle

/**
 * Selects the [AntiTamperPolicy] strategy for the current device. Single
 * candidate; factory shape kept for uniformity. Returns `null` when no strategy
 * is supported (e.g. not Device Owner, or below API 24), in which case
 * `antiTamper` is never advertised.
 */
object AntiTamperPolicyFactory {

    fun create(handle: DpmHandle): AntiTamperPolicy? =
        listOf(AntiTamperRestrictionPolicy(handle)).firstOrNull { it.isSupported() }
}
