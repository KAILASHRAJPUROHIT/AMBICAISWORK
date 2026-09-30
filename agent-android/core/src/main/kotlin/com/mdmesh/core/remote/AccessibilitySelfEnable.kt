package com.mdmesh.core.remote

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageManager
import android.provider.Settings
import android.util.Log

/**
 * Turns on [ScreenCaptureAccessibilityService] without anyone opening Settings.
 *
 * A Device Owner may grant itself the development-level `WRITE_SECURE_SETTINGS` permission through
 * `setPermissionGrantState`; with it the agent can add its own service to
 * `Settings.Secure.enabled_accessibility_services`. Without this the remote-view "screen" source
 * (and remote input) never works on a kiosk tablet, because staff cannot reach the Accessibility
 * settings screen. Best effort: some OEM builds refuse the grant, in which case the manual
 * checklist row remains the fallback.
 */
object AccessibilitySelfEnable {
    private const val TAG = "A11ySelfEnable"
    private const val WRITE_SECURE = "android.permission.WRITE_SECURE_SETTINGS"

    /** @return true when the service is (now) listed as enabled. */
    fun ensure(context: Context, admin: ComponentName): Boolean {
        val app = context.applicationContext
        if (ScreenCaptureAccessibilityService.isConnected()) return true
        val dpm = app.getSystemService(Context.DEVICE_POLICY_SERVICE) as? DevicePolicyManager ?: return false
        if (!dpm.isDeviceOwnerApp(app.packageName)) return false

        if (app.checkSelfPermission(WRITE_SECURE) != PackageManager.PERMISSION_GRANTED) {
            runCatching {
                dpm.setPermissionGrantState(admin, app.packageName, WRITE_SECURE, DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED)
            }.onFailure { Log.w(TAG, "self-grant of WRITE_SECURE_SETTINGS refused", it) }
            if (app.checkSelfPermission(WRITE_SECURE) != PackageManager.PERMISSION_GRANTED) return false
        }

        val service = ComponentName(app, ScreenCaptureAccessibilityService::class.java).flattenToString()
        return runCatching {
            val cr = app.contentResolver
            val current = Settings.Secure.getString(cr, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES).orEmpty()
            val entries = current.split(':').filter { it.isNotBlank() }
            if (service !in entries) {
                Settings.Secure.putString(cr, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES, (entries + service).joinToString(":"))
            }
            Settings.Secure.putInt(cr, Settings.Secure.ACCESSIBILITY_ENABLED, 1)
            true
        }.onFailure { Log.w(TAG, "could not enable accessibility service", it) }.getOrDefault(false)
    }
}
