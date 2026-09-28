package com.mdmesh.core.telemetry

import android.app.AppOpsManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.os.Process
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Low-power app-usage log: turns Android's own usage history into one `appUsage` event per app
 * session ("com.pkg|Label|seconds", ts = session start), buffered in [EventLog] and uploaded
 * with the next normal check-in.
 *
 * Power: no timers or polling of our own. Android records foreground/background transitions
 * regardless; [collect] just reads the new ones since the last check-in (one cheap query).
 * Privacy: only which app was in the foreground and for how long -- no content, URLs,
 * keystrokes or screenshots.
 *
 * Needs the usage-access AppOp (GET_USAGE_STATS). Like WRITE_SETTINGS it resets on every agent
 * update; the shop PC's tools/appop-guardian.py re-grants both. Without it [collect] is a no-op.
 */
@Singleton
class ActivityLogger @Inject constructor(
    @ApplicationContext private val context: Context,
    private val events: EventLog,
) {
    private val prefs = context.getSharedPreferences("mdm_activity", Context.MODE_PRIVATE)

    fun hasUsageAccess(): Boolean = runCatching {
        val ops = context.getSystemService(AppOpsManager::class.java)
        @Suppress("DEPRECATION")
        ops.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), context.packageName) ==
            AppOpsManager.MODE_ALLOWED
    }.getOrDefault(false)

    @Synchronized
    fun collect() {
        if (!hasUsageAccess()) return
        val usm = context.getSystemService(UsageStatsManager::class.java) ?: return
        val now = System.currentTimeMillis()
        val since = prefs.getLong(KEY_SINCE, now - FIRST_WINDOW_MS).coerceIn(now - MAX_WINDOW_MS, now)
        val batch = runCatching { usm.queryEvents(since, now) }.getOrNull() ?: return

        // Session state carried across check-ins (an app can stay open past a check-in).
        var current = prefs.getString(KEY_CUR_PKG, null)
        var start = prefs.getLong(KEY_CUR_START, 0L)
        var lastPause = prefs.getLong(KEY_LAST_PAUSE, 0L).takeIf { it > 0 }

        val e = UsageEvents.Event()
        while (batch.hasNextEvent()) {
            batch.getNextEvent(e)
            val pkg = e.packageName ?: continue
            if (pkg in IGNORED) continue
            when (e.eventType) {
                UsageEvents.Event.ACTIVITY_RESUMED -> {
                    val t = e.timeStamp
                    if (pkg == current) {
                        // Same app again: a quick pause/resume (activity switch inside the app)
                        // continues the session; a longer gap starts a new one.
                        if (lastPause != null && t - lastPause > MERGE_GAP_MS) {
                            emit(current, start, lastPause)
                            start = t
                        }
                    } else {
                        if (current != null) emit(current, start, lastPause ?: t)
                        current = pkg
                        start = t
                    }
                    lastPause = null
                }
                UsageEvents.Event.ACTIVITY_PAUSED -> if (pkg == current) lastPause = e.timeStamp
            }
        }
        // Close a session whose app was left (paused) and not resumed within the merge gap.
        if (current != null && lastPause != null && now - lastPause > MERGE_GAP_MS) {
            emit(current, start, lastPause)
            current = null
            lastPause = null
        }

        prefs.edit()
            .putLong(KEY_SINCE, now)
            .putString(KEY_CUR_PKG, current)
            .putLong(KEY_CUR_START, start)
            .putLong(KEY_LAST_PAUSE, lastPause ?: 0L)
            .apply()
    }

    private fun emit(pkg: String, start: Long, end: Long) {
        val seconds = (end - start) / 1000
        if (seconds < MIN_SESSION_S) return
        val label = runCatching {
            val pm = context.packageManager
            pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString()
        }.getOrDefault(pkg)
        events.recordAt(EVENT_APP_USAGE, start, "$pkg|${label.replace('|', '/')}|$seconds")
    }

    companion object {
        const val EVENT_APP_USAGE = "appUsage"
        private const val KEY_SINCE = "since"
        private const val KEY_CUR_PKG = "curPkg"
        private const val KEY_CUR_START = "curStart"
        private const val KEY_LAST_PAUSE = "lastPause"
        private const val FIRST_WINDOW_MS = 15 * 60_000L
        private const val MAX_WINDOW_MS = 24 * 3_600_000L
        private const val MERGE_GAP_MS = 3_000L
        private const val MIN_SESSION_S = 1L
        // System chrome that "resumes" constantly and says nothing about what staff did.
        private val IGNORED = setOf("com.android.systemui", "android")
    }
}
