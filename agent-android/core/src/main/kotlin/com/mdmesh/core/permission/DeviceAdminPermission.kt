package com.mdmesh.core.permission

import android.app.admin.DevicePolicyManager
import android.content.Context
import android.content.Intent

/**
 * Always satisfied by the time [com.mdmesh.agent.PermissionsChecklistActivity] is reachable —
 * Device-Owner provisioning implies it, and the Lite-tier link screen
 * ([com.mdmesh.agent.LinkDeviceActivity]) already activates Device Admin before this screen can
 * open. Kept as a row purely for visual/positional parity with the familiar 8-row checklist
 * layout; tapping it re-opens the system activation prompt as a fallback only.
 */
object DeviceAdminPermission : PermissionCheck {
    override val key = "deviceAdmin"
    override val label = "Activate Device Admin"
    override val description = "Required to manage this device. Already active by the time you reach this screen."
    override val verifiable = true
    override val skippable = false

    override fun isGranted(context: Context): Boolean {
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        return dpm.activeAdmins?.any { it.packageName == context.packageName } == true
    }

    override fun settingsIntent(context: Context): Intent {
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        val admin = dpm.activeAdmins?.firstOrNull { it.packageName == context.packageName }
        return Intent(DevicePolicyManager.ACTION_ADD_DEVICE_ADMIN).apply {
            admin?.let { putExtra(DevicePolicyManager.EXTRA_DEVICE_ADMIN, it) }
        }
    }
}
