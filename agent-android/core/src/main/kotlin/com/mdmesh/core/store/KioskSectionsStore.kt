package com.mdmesh.core.store

import android.content.Context
import android.content.SharedPreferences
import com.mdmesh.proto.KioskSections
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * The console's per-section switches (Settings > Kiosk sections), delivered on every check-in and
 * cached so the kiosk applies them at boot and offline. [KEY_VERSION] is bumped only when the value
 * actually changes, which is what the kiosk listens for to re-draw.
 */
@Singleton
class KioskSectionsStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    fun apply(json: String?) {
        val normalised = json?.takeIf { it.isNotBlank() }
        val p = prefs(context)
        if (p.getString(KEY_JSON, null) == normalised) return
        p.edit().putString(KEY_JSON, normalised).putLong(KEY_VERSION, System.currentTimeMillis()).apply()
    }

    companion object {
        const val PREFS = "kiosk_sections"
        const val KEY_VERSION = "version"
        private const val KEY_JSON = "json"

        fun prefs(context: Context): SharedPreferences = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

        fun read(context: Context): KioskSections = KioskSections.parse(prefs(context).getString(KEY_JSON, null))
    }
}
