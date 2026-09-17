package com.mdmesh.policy.frp

import android.app.admin.FactoryResetProtectionPolicy
import android.os.Build
import android.content.Intent
import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.wifi.DpmHandle

/**
 * FRP strategy via [android.app.admin.DevicePolicyManager.setFactoryResetProtectionPolicy]
 * API 30+ Google EFRP. Recovery IDs come from an authenticated tenant policy command.
 * Missing configuration must never write an empty or email-based enabled policy.
 */
internal class FrpProtectionPolicy(
    private val handle: DpmHandle,
) : FrpPolicy {

    override val capabilityKey: String = FrpPolicy.CAPABILITY_KEY

    override fun isSupported(): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.R &&
            handle.dpm.isDeviceOwnerApp(handle.admin.packageName)

    override fun setEnabled(enabled: Boolean): PolicyOutcome =
        if (enabled) PolicyOutcome.Failed("FRP enable requires verified recoveryAccountIds; legacy on/off command rejected")
        else applyPolicy(false, emptyList())

    override fun enableWithAccounts(accountIds: List<String>): PolicyOutcome = applyPolicy(true, accountIds)

    private fun applyPolicy(enabled: Boolean, accountIds: List<String>): PolicyOutcome = runCatching {
        // Redundant with isSupported()'s gate at runtime (CapabilityRegistry never calls
        // setEnabled on an unsupported device), but Lint's NewApi check can't see across that
        // method boundary — this local guard is what actually silences the API-30 warning on
        // FactoryResetProtectionPolicy.Builder() below.
        if (!isSupported()) return PolicyOutcome.Unsupported
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return PolicyOutcome.Unsupported
        val accounts = if (enabled) FrpAccountIds.parse(accountIds.joinToString(",")) else emptyList()
        val policy = if (enabled) {
            FactoryResetProtectionPolicy.Builder()
                .setFactoryResetProtectionAccounts(accounts)
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
        handle.context.sendBroadcast(
            Intent("com.google.android.gms.auth.FRP_CONFIG_CHANGED").setPackage("com.google.android.gms"),
        )
        val actual = handle.dpm.getFactoryResetProtectionPolicy(handle.admin)
        check(actual != null && actual.isFactoryResetProtectionEnabled == enabled &&
            actual.factoryResetProtectionAccounts.toSet() == accounts.toSet()) {
            "FRP read-back mismatch; do not reset this device"
        }
        PolicyOutcome.Applied
    }.getOrElse { PolicyOutcome.Failed(it.message ?: "factoryResetProtection setEnabled failed") }

}
