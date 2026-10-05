package com.mdmesh.core.update

/**
 * Rules for asking the person using the device before the agent updates itself (the update restarts the app).
 * Pure functions so the timings can be unit tested.
 *
 *  - The popup stays up for [OFFER_SECONDS]. No answer counts as "Update now", so an unattended update is never stuck.
 *  - "Update later" postpones by [DEFER_MINUTES] and then waits for the device to be idle (screen off) before applying,
 *    so nobody is interrupted mid-sale.
 *  - A postponed update is not allowed to wait forever: once [MAX_DEFER_HOURS] have passed since it was first offered,
 *    "Update later" is no longer available.
 */
object UpdateConsentPolicy {
    const val OFFER_SECONDS = 60
    const val DEFER_MINUTES = 30L
    const val MAX_DEFER_HOURS = 24L

    private const val MINUTE_MS = 60_000L
    private const val HOUR_MS = 60 * MINUTE_MS

    /** Nobody is looking at a device whose screen is off, so there is nothing to ask: update straight away. */
    fun needsPopup(screenInteractive: Boolean): Boolean = screenInteractive

    /** Whether "Update later" may still be offered for an update first offered at [firstOfferedAt]. */
    fun canDefer(firstOfferedAt: Long, now: Long): Boolean = now - firstOfferedAt < MAX_DEFER_HOURS * HOUR_MS

    fun deferUntil(now: Long): Long = now + DEFER_MINUTES * MINUTE_MS

    /** What to do with a postponed update right now. */
    enum class DeferredAction { WAIT, APPLY_NOW, ASK_AGAIN }

    fun deferredAction(now: Long, deferUntil: Long, firstOfferedAt: Long, screenInteractive: Boolean): DeferredAction = when {
        now < deferUntil -> DeferredAction.WAIT
        !screenInteractive -> DeferredAction.APPLY_NOW            // idle: apply without disturbing anyone
        !canDefer(firstOfferedAt, now) -> DeferredAction.ASK_AGAIN // overdue: ask again, this time without "later"
        else -> DeferredAction.WAIT                                // still in use: keep waiting for an idle moment
    }

    /** A popup nobody answered, nor closed: it was lost (activity killed). Treat as no answer. */
    fun offerExpired(now: Long, deadline: Long): Boolean = now >= deadline + 5_000L
}
