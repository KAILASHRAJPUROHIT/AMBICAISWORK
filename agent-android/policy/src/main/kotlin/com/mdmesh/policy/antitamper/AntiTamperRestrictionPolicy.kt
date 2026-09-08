package com.mdmesh.policy.antitamper

import android.os.Build
import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.UserRestrictions
import com.mdmesh.policy.wifi.DpmHandle

/**
 * Anti-tamper strategy via the `DISALLOW_FACTORY_RESET` + `DISALLOW_SAFE_BOOT` +
 * `DISALLOW_DEBUGGING_FEATURES` user restrictions.
 *
 * Unlike the other toggles, `enabled=true` here means the *protection* is ON (the
 * restrictions are applied) — the natural reading for a capability named
 * "anti-tamper", the inverse of [com.mdmesh.policy.usb.UsbStorageRestrictionPolicy]'s
 * "feature available" convention. All three restrictions exist from API 21, but
 * `DISALLOW_SAFE_BOOT` is only honoured from API 24 (the module floor), so the
 * bundle is meaningful on every supported device.
 */
internal class AntiTamperRestrictionPolicy(
    private val handle: DpmHandle,
) : AntiTamperPolicy {

    override val capabilityKey: String = AntiTamperPolicy.CAPABILITY_KEY

    private val restrictions: Set<String> =
        UserRestrictions.forKey(AntiTamperPolicy.CAPABILITY_KEY).orEmpty()

    override fun isSupported(): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.N &&
            handle.dpm.isDeviceOwnerApp(handle.admin.packageName)

    override fun setEnabled(enabled: Boolean): PolicyOutcome = runCatching {
        restrictions.forEach { key ->
            if (enabled) {
                handle.dpm.addUserRestriction(handle.admin, key)
            } else {
                handle.dpm.clearUserRestriction(handle.admin, key)
            }
        }
        PolicyOutcome.Applied
    }.getOrElse { PolicyOutcome.Failed(it.message ?: "antiTamper setEnabled failed") }
}
