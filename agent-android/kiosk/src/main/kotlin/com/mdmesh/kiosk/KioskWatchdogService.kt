package com.mdmesh.kiosk

import android.accessibilityservice.AccessibilityService
import android.app.ActivityManager
import android.content.Intent
import android.view.accessibility.AccessibilityEvent

/**
 * Watchdog for the "Lite" tier's [SoftPinKioskController]. Device Owner's real lock-task has no
 * escape gesture; a plain `Activity.startLockTask()` pin does — holding Back+Recents together
 * always exits it, unconditionally, as a hardcoded Android framework behavior with no override
 * available to a non-Device-Owner caller. This service cannot prevent that exit (nothing can),
 * only detect it and relaunch immediately, closing the window as fast as an accessibility event
 * dispatch allows.
 *
 * Deliberately separate from [com.mdmesh.remote] `InputInjectionService` — that service injects
 * gestures and is architected to never observe events (its own doc comment: "it injects, it does
 * not snoop"), for Play-Protect-surface-minimization reasons that should not be complicated by
 * folding in an unrelated concern. This service is the mirror case: it only *observes*
 * `TYPE_WINDOW_STATE_CHANGED`, injects nothing, and lives in its own manifest scope (`:kiosk`,
 * not `:app`) — `android:enabled="false"` by default, toggled on/off by
 * [SoftPinKioskController]'s caller exactly when Lite kiosk is entered/exited, so it is never
 * running except while actively needed.
 *
 * The signal is deliberately [ActivityManager.lockTaskModeState], not "foreground package
 * changed": a legitimate in-kiosk app switch (the user opening an allowed app from the launcher
 * grid, or the pinned single app itself coming to the foreground) also changes the foreground
 * package without ever leaving lock-task mode, and must NOT trigger a relaunch — only a real
 * `LOCK_TASK_MODE_NONE` transition means the escape gesture actually fired.
 */
class KioskWatchdogService : AccessibilityService() {

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        if (event.eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) return
        val am = getSystemService(ACTIVITY_SERVICE) as? ActivityManager ?: return
        if (am.lockTaskModeState != ActivityManager.LOCK_TASK_MODE_NONE) return
        // Lock task was exited (the Back+Recents escape) while this watchdog was armed —
        // relaunch immediately via the real HOME intent, same pattern used everywhere else in
        // this codebase (KioskEnterHandler.foregroundLauncher, MainActivity.reenterKiosk):
        // resolving through ACTION_MAIN/CATEGORY_HOME re-triggers the OEM System UI's normal
        // home-transition path, not just a direct component launch.
        runCatching {
            startActivity(
                Intent(Intent.ACTION_MAIN)
                    .addCategory(Intent.CATEGORY_HOME)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        }
    }

    override fun onInterrupt() {}
}
