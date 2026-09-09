package com.mdmesh.policy.frp

import android.app.admin.FactoryResetProtectionPolicy
import android.os.Build
import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.wifi.DpmHandle

/**
 * FRP strategy via [android.app.admin.DevicePolicyManager.setFactoryResetProtectionPolicy]
 * (API 30+). The recovery account is fixed rather than admin-configurable per device —
 * matching the single-business-account fleet model — so the payload carries no data
 * beyond on/off; only the account below can clear a locked device after a wipe.
 */
internal class FrpProtectionPolicy(
    private val handle: DpmHandle,
) : FrpPolicy {

    override val capabilityKey: String = FrpPolicy.CAPABILITY_KEY

    override fun isSupported(): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.R &&
            handle.dpm.isDeviceOwnerApp(handle.admin.packageName)

    override fun setEnabled(enabled: Boolean): PolicyOutcome = runCatching {
        // Redundant with isSupported()'s gate at runtime (CapabilityRegistry never calls
        // setEnabled on an unsupported device), but Lint's NewApi check can't see across that
        // method boundary — this local guard is what actually silences the API-30 warning on
        // FactoryResetProtectionPolicy.Builder() below.
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return PolicyOutcome.Unsupported
        val policy = if (enabled) {
            FactoryResetProtectionPolicy.Builder()
                .setFactoryResetProtectionAccounts(listOf(RECOVERY_ACCOUNT))
                .setFactoryResetProtectionEnabled(true)
                .build()
        } else {
            // Clearing the account list + disabling is the documented way to remove FRP.
            FactoryResetProtectionPolicy.Builder()
                .setFactoryResetProtectionAccounts(emptyList())
                .setFactoryResetProtectionEnabled(false)
                .build()
        }
        handle.dpm.setFactoryResetProtectionPolicy(handle.admin, policy)
        PolicyOutcome.Applied
    }.getOrElse { PolicyOutcome.Failed(it.message ?: "factoryResetProtection setEnabled failed") }

    private companion object {
        // The fleet's recovery account — whoever signs in with this after an FRP-protected
        // wipe can unlock the device. Keep this owned by the business, not an individual.
        const val RECOVERY_ACCOUNT = "info@aradhanajewellers.com"
    }
}
