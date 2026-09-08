package com.mdmesh.policy.frp

import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.TogglePolicy

/**
 * Capability-abstracted Factory Reset Protection control.
 *
 * `setEnabled(true)` requires the configured recovery account to unlock the
 * device after any factory reset — including a Recovery-mode wipe, which bypasses
 * the kiosk/Device-Owner app entirely and is otherwise unrecoverable-by-us once
 * done. `setEnabled(false)` clears the policy (e.g. before a legitimate resale/
 * repurpose reset). Backed by
 * [android.app.admin.DevicePolicyManager.setFactoryResetProtectionPolicy] (API 30+).
 * The single concrete strategy ([FrpProtectionPolicy]) is selected by
 * [FrpPolicyFactory].
 */
interface FrpPolicy : TogglePolicy {

    override fun setEnabled(enabled: Boolean): PolicyOutcome

    companion object {
        const val CAPABILITY_KEY = "factoryResetProtection"
    }
}
