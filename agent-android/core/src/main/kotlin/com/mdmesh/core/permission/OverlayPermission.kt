package com.mdmesh.core.permission

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings

/**
 * Reserved for a future Lite-tier lock/notice overlay — Device-Owner devices already get a
 * hard kiosk lock via `LockTaskKioskController`; this would back an equivalent on-screen notice
 * for Lite devices, where lock-task alone is escapable via Back+Recents. No feature consumes
 * this yet.
 */
object OverlayPermission : PermissionCheck {
    override val key = "overlay"
    override val label = "Enable Overlay Permission"
    override val description = "Allows the agent to show an on-screen notice over other apps (used for future kiosk features)."
    override val verifiable = true
    override val skippable = true

    override fun isGranted(context: Context): Boolean =
        Settings.canDrawOverlays(context)

    override fun settingsIntent(context: Context): Intent =
        Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:${context.packageName}"))
}
