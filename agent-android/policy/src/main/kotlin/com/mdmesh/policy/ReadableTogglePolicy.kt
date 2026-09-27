package com.mdmesh.policy

/**
 * A [TogglePolicy] whose current state can also be read back.
 *
 * The remote `policy.apply` command path never needed this — it only ever writes
 * ([PolicyApplyHandler] fires-and-forgets a `setEnabled` call). The on-device quick-controls
 * panel is different: it has to show the user whether auto-rotation, auto-brightness, or
 * flight mode is *currently* on before they touch anything, so it needs a getter these
 * existing toggles (wifi, camera, bluetooth, ...) never had to provide.
 *
 * Returns `null` when the state genuinely cannot be determined (rather than guessing),
 * mirroring [PolicyOutcome.Unsupported]'s "degrade, don't lie" contract.
 */
interface ReadableTogglePolicy : TogglePolicy {
    fun isEnabled(): Boolean?
}
