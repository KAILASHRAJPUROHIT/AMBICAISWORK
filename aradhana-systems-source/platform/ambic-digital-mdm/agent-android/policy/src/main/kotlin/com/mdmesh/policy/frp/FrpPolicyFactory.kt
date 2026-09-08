package com.mdmesh.policy.frp

import com.mdmesh.policy.wifi.DpmHandle

/**
 * Selects the [FrpPolicy] strategy for the current device. Single candidate;
 * factory shape kept for uniformity. Returns `null` when no strategy is
 * supported (e.g. not Device Owner, or below API 30), in which case
 * `factoryResetProtection` is never advertised.
 */
object FrpPolicyFactory {

    fun create(handle: DpmHandle): FrpPolicy? =
        listOf(FrpProtectionPolicy(handle)).firstOrNull { it.isSupported() }
}
