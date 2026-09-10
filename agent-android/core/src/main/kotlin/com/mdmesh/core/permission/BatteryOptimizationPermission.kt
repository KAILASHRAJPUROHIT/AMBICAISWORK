package com.mdmesh.core.permission

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings

/**
 * Moved here from `LinkDeviceActivity`'s old one-off `offerBatteryExemption()` — now one
 * implementation instead of two. No Device-Admin-level silent grant exists for it, so it
 * needs the same user-facing system prompt on every device tier.
 */
object BatteryOptimizationPermission : PermissionCheck {
    override val key = "batteryOptimization"
    override val label = "Ignore Battery Optimization"
    override val description = "Keeps the management connection alive while the device is idle."
    override val verifiable = true
    override val skippable = true

    override fun isGranted(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return true
        val pm = context.getSystemService(Context.POWER_SERVICE) as PowerManager
        return pm.isIgnoringBatteryOptimizations(context.packageName)
    }

    override fun settingsIntent(context: Context): Intent =
        Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${context.packageName}"))
}
