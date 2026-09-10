package com.mdmesh.core.permission

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings

/** Reserved for future brightness/rotation/screen-timeout control commands. No feature
 *  consumes this yet. */
object WriteSettingsPermission : PermissionCheck {
    override val key = "writeSettings"
    override val label = "Enable Write System Settings"
    override val description = "Allows the agent to change device brightness, rotation, and timeout (used for future features)."
    override val verifiable = true
    override val skippable = true

    override fun isGranted(context: Context): Boolean =
        Settings.System.canWrite(context)

    override fun settingsIntent(context: Context): Intent =
        Intent(Settings.ACTION_MANAGE_WRITE_SETTINGS, Uri.parse("package:${context.packageName}"))
}
