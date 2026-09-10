package com.mdmesh.core.permission

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.Settings
import androidx.core.content.ContextCompat

/**
 * Needed for on-device file access (log export, staged certificates). API 30+ uses the
 * "All files access" special grant; below that, the legacy `WRITE_EXTERNAL_STORAGE` runtime
 * permission (declared `maxSdkVersion="29"` in the manifest, matching the platform's own
 * scoped-storage migration).
 */
object ExternalStoragePermission : PermissionCheck {
    override val key = "externalStorage"
    override val label = "External Storage Access"
    override val description = "Allows the agent to read/write files on device storage."
    override val verifiable = true
    override val skippable = true

    override fun isGranted(context: Context): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            Environment.isExternalStorageManager()
        } else {
            ContextCompat.checkSelfPermission(context, android.Manifest.permission.WRITE_EXTERNAL_STORAGE) ==
                PackageManager.PERMISSION_GRANTED
        }

    override fun settingsIntent(context: Context): Intent =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            Intent(
                Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                Uri.parse("package:${context.packageName}"),
            )
        } else {
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${context.packageName}"))
        }
}
