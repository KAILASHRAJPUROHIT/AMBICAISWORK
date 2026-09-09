package com.mdmesh.kiosk

import android.app.ActivityManager
import android.content.ComponentName
import android.content.Context

/**
 * "Lite" tier (Device Admin only, no Device Owner) kiosk fallback.
 *
 * There is no non-Device-Owner equivalent of `setLockTaskPackages`/`setLockTaskFeatures`/
 * `addPersistentPreferredActivity` — those `DevicePolicyManager` calls are DO/PO-only, full
 * stop. Plain `Activity.startLockTask()`/`stopLockTask()` (available to any app, on itself) is
 * already called unconditionally from [com.mdmesh.agent.KioskLauncherActivity]'s own
 * `startLockTaskSafely`/`stopLockTaskSafely` — that call site does not depend on this class at
 * all. So [enter]/[exit] here do no DPM work; they exist only so the existing `kiosk.enter`
 * command flow (which gates on [KioskResult] before persisting the payload — see
 * `KioskEnterHandler`) has something to succeed against, letting the launcher activity's
 * already-unconditional lock-task calls do the actual pinning once it comes to the foreground.
 *
 * Two real, disclosed limitations vs. the Device-Owner path:
 *  - **Escapable.** The first `startLockTask()` shows a one-time system consent dialog, and
 *    holding Back+Recents together always exits pinning — a hardcoded Android framework
 *    behavior with no override for a non-DO caller, by design. A watchdog can detect and re-pin
 *    quickly; it cannot prevent the exit.
 *  - **Single-task, not an allowlist.** `startLockTask()` locks the current *task*, not a set of
 *    packages — there is no DPM-level enforcement stopping a user from reaching another app if
 *    it launches outside the pinned task. The launcher UI still only *offers* the configured
 *    allowlist (same `KioskApplyPayload`-driven grid as the DO path), so casual navigation is
 *    still constrained; a determined user is not blocked at the OS level the way DO's real
 *    allowlist blocks them.
 */
class SoftPinKioskController : KioskController {

    override fun enter(homeComponent: ComponentName, allowedPackages: List<String>, features: Int): KioskResult =
        KioskResult.Ok

    override fun exit(): KioskResult = KioskResult.Ok

    override fun isLocked(context: Context): Boolean = runCatching {
        val am = context.getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager
        am?.lockTaskModeState != ActivityManager.LOCK_TASK_MODE_NONE
    }.getOrDefault(false)

    /** No DPM-level allowlist exists for the Lite tier — the launcher UI's own configured
     *  `KioskApplyPayload.allowedPackages` (persisted separately in `KioskStateStore`) is the
     *  only "allowlist" that exists; this always reports empty since there is nothing enforced
     *  at this layer to report. */
    override fun allowedPackages(): List<String> = emptyList()
}
