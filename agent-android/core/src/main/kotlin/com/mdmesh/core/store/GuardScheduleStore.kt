package com.mdmesh.core.store

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/** The shop-closed hours (console Settings > Security), delivered on every check-in and cached for offline use. */
@Singleton
class GuardScheduleStore @Inject constructor(@ApplicationContext private val context: Context) {
    fun apply(raw: String?) {
        val v = raw?.takeIf { it.isNotBlank() }
        val p = prefs(context)
        if (p.getString(KEY, null) == v) return
        p.edit().putString(KEY, v).apply()
    }

    companion object {
        private const val PREFS = "guard_schedule"
        private const val KEY = "quietHours"
        private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

        /** The raw setting (`HH:MM-HH:MM`, `off`, or null for the default). */
        fun read(context: Context): String? = prefs(context).getString(KEY, null)
    }
}
