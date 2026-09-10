package com.mdmesh.core.permission

import android.content.Context
import android.content.Intent
import android.provider.Settings

/**
 * No public Android API exists to read the current assist-app selection — this is a one-way
 * action (open the system screen, the admin manually sets it to "None"), not a verifiable
 * toggle. Always renders as unconfirmed; always skippable.
 */
object DisableAssistPermission : PermissionCheck {
    override val key = "disableAssist"
    override val label = "Disable Assist App"
    override val description = "Open Assist app settings and select None to disable the long-press-home gesture."
    override val verifiable = false
    override val skippable = true

    override fun isGranted(context: Context): Boolean = false

    override fun settingsIntent(context: Context): Intent =
        Intent(Settings.ACTION_VOICE_INPUT_SETTINGS)
}
