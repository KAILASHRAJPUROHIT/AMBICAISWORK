package com.mdmesh.core.net

import android.content.Context

/**
 * Per-device switch for the offline protection (full-screen "no internet" message, lockdown, Wi-Fi hunting and location reports).
 * Turned off from the console with `device.guardMode` for a tablet that should never lock, for example while outgoing email is
 * not set up and nobody could receive the unlock code. On by default.
 */
object GuardSwitch {
    private const val PREFS = "mdm_guard_switch"
    private const val KEY = "enabled"

    fun isEnabled(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(KEY, true)

    fun set(context: Context, enabled: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean(KEY, enabled).apply()
    }
}

/** What the protection is doing right now, for telemetry: "on", "off" or "lockdown". */
object GuardStatus {
    @Volatile var lockdown: Boolean = false
}
