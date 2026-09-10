package com.mdmesh.core.permission

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings

/**
 * Backs future Lite-tier (Device-Admin-only) manual APK installs — Lite devices can't get
 * silent installs the way Device-Owner devices can via the PackageInstaller session APIs, so a
 * Lite device that needs to install a pushed APK must have Unknown Sources allowed first.
 */
object UnknownSourcesPermission : PermissionCheck {
    override val key = "unknownSources"
    override val label = "Install from Unknown Sources"
    override val description = "Allows installing apps pushed from the console outside the Play Store."
    override val verifiable = true
    override val skippable = true

    override fun isGranted(context: Context): Boolean =
        context.packageManager.canRequestPackageInstalls()

    override fun settingsIntent(context: Context): Intent =
        Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}"))
}
