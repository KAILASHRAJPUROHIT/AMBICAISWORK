package com.mdmesh.core.permission

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Context
import android.content.Intent
import android.provider.Settings
import android.view.accessibility.AccessibilityManager

/**
 * Backed by `com.mdmesh.core.remote.ScreenCaptureAccessibilityService` — used only for its
 * [android.accessibilityservice.AccessibilityService.takeScreenshot] capability (API 30+), the
 * one silent (no per-call consent dialog, no persistent "recording" notification) way to capture
 * the screen for a remote-view session. Unlike a runtime permission, Device Owner cannot enable an
 * accessibility service on the admin's behalf — `setPermittedAccessibilityServices` only
 * *allowlists* it, the toggle itself needs `WRITE_SECURE_SETTINGS`, which Device Owner does not
 * hold — so, like the other rows in this checklist, this is a one-time manual step, not something
 * a `kiosk.enter`/enrollment flow can silently do.
 */
object ScreenCaptureAccessibilityPermission : PermissionCheck {
    override val key = "screenCaptureAccessibility"
    override val label = "Enable Screen Capture (remote view)"
    override val description =
        "Lets the console take periodic screenshots during a remote-view session, started from the admin console. No effect otherwise."
    override val verifiable = true
    override val skippable = true

    override fun isGranted(context: Context): Boolean {
        if (com.mdmesh.core.remote.ScreenCaptureAccessibilityService.isConnected()) return true
        val am = context.getSystemService(Context.ACCESSIBILITY_SERVICE) as? AccessibilityManager ?: return false
        val pkg = context.packageName
        return am.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
            .any { it.id.startsWith("$pkg/") && it.id.endsWith("ScreenCaptureAccessibilityService") }
    }

    override fun settingsIntent(context: Context): Intent =
        Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
}
