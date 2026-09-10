package com.mdmesh.core.permission

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings

/**
 * Backs future Lite-tier (Device-Admin-only) manual APK installs — Lite devices can't get
 * silent installs the way Device-Owner devices can via the PackageInstaller session APIs, so a
 * Lite device that needs to install a pushed APK must have Unknown Sources allowed first.
 * `canRequestPackageInstalls()` needs API 26+ (this project's minSdk is 24) — below that, the
 * per-app toggle didn't exist yet (installs were gated by a single global system setting
 * instead), so this row treats a pre-26 device as already satisfied.
 */
object UnknownSourcesPermission : PermissionCheck {
    override val key = "unknownSources"
    override val label = "Install from Unknown Sources"
    override val description = "Allows installing apps pushed from the console outside the Play Store."
    override val verifiable = true
    override val skippable = true

    override fun isGranted(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return true
        return context.packageManager.canRequestPackageInstalls()
    }

    override fun settingsIntent(context: Context): Intent =
        Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}"))
}
