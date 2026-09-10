package com.mdmesh.core.permission

import android.content.Context
import android.content.Intent

/**
 * One row of the on-device permissions checklist ([com.mdmesh.agent.PermissionsChecklistActivity]).
 * Each implementation wraps a single Android special-access grant: how to check whether it's
 * currently held, and what Settings screen opens to request it. Modeled after
 * [com.mdmesh.policy.PolicyStrategy] (`isSupported()` there, `isGranted()` here), adapted for
 * local on-device permission state instead of a remotely-commanded DPM policy.
 */
interface PermissionCheck {
    val key: String
    val label: String
    val description: String

    /** False only for [DisableAssistPermission] — no public API exists to read the current
     *  assist-app selection, so that row can never programmatically confirm itself. */
    val verifiable: Boolean

    /** Whether a "Skip" action is offered for this row. */
    val skippable: Boolean

    fun isGranted(context: Context): Boolean
    fun settingsIntent(context: Context): Intent
}
