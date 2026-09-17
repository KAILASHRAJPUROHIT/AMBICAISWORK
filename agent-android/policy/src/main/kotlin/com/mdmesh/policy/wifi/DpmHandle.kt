package com.mdmesh.policy.wifi

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context

/**
 * Thin holder bundling the [DevicePolicyManager] with this agent's admin
 * [ComponentName]. Passed to every strategy so that the raw DPM surface stays
 * confined to the strategy implementations and never leaks into feature code.
 */
data class DpmHandle(
    val dpm: DevicePolicyManager,
    val admin: ComponentName,
    val context: Context,
)
