package com.mdmesh.core.permission

import android.app.AppOpsManager
import android.content.Context
import android.content.Intent
import android.os.Process
import android.provider.Settings

/**
 * Backs [com.mdmesh.core.telemetry.NetworkUsageCollector], which today silently returns `null`
 * until this is granted — an AppOps special-access permission, not a manifest runtime one, so
 * it is **not** silently grantable via Device Owner. Every device needs this row walked through
 * manually, DO or Lite alike.
 */
object UsageAccessPermission : PermissionCheck {
    override val key = "usageAccess"
    override val label = "Allow Usage Access"
    override val description = "Enables data-usage tracking (cellular/Wi-Fi bytes) in the console."
    override val verifiable = true
    override val skippable = true

    override fun isGranted(context: Context): Boolean {
        val appOps = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = appOps.checkOpNoThrow(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            Process.myUid(),
            context.packageName,
        )
        return mode == AppOpsManager.MODE_ALLOWED
    }

    override fun settingsIntent(context: Context): Intent =
        Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)
}
