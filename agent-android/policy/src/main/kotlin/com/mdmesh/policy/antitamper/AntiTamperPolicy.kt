package com.mdmesh.policy.antitamper

import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.TogglePolicy

/**
 * Capability-abstracted "close the local escape hatches" control.
 *
 * `setEnabled(true)` blocks Settings-menu factory reset, Safe Mode boot, and
 * USB-debugging/ADB access (restrictions added); `setEnabled(false)` restores them
 * (restrictions cleared). Backed by [UserRestrictions.forKey]`("antiTamper")`. The
 * single concrete strategy ([AntiTamperRestrictionPolicy]) is selected by
 * [AntiTamperPolicyFactory].
 */
interface AntiTamperPolicy : TogglePolicy {

    override fun setEnabled(enabled: Boolean): PolicyOutcome

    companion object {
        const val CAPABILITY_KEY = "antiTamper"
    }
}
