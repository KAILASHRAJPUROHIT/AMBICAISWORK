package com.mdmesh.core.net

/** The owner's connectivity rules, as numbers. */
object GuardTimings {
    /** Wi-Fi turned off by hand is switched back on after this long (at boot it is switched on at once). */
    const val WIFI_REENABLE_MS = 3 * 60_000L
    /** No internet this long: full-screen "device unusable without internet" message. */
    const val BLOCK_AFTER_MS = 10 * 60_000L
    /** No internet this long: complete lockdown until an administrator unlocks it with an emailed code. */
    const val LOCKDOWN_AFTER_MS = 30 * 60_000L
    const val ENABLE_RETRY_MS = 30_000L
    const val RECONNECT_EVERY_MS = 20_000L
    const val HUNT_EVERY_MS = 60_000L
    const val REPORT_EVERY_MS = 2 * 60_000L
}

data class GuardState(
    val wifiOffSince: Long? = null,
    val offlineSince: Long? = null,
    /** Persisted: survives reboots and only an administrator can clear it. */
    val lockdown: Boolean = false,
    val bootPending: Boolean = false,
    val lastEnableAt: Long = 0L,
    val lastReconnectAt: Long = 0L,
    val lastHuntAt: Long = 0L,
    val lastReportAt: Long = 0L,
    val reconnectAttempts: Int = 0,
    /** The previous tick was inside the shop-closed window with the tablet sitting still (nothing was counting). */
    val suspended: Boolean = false,
)

data class GuardInput(
    val now: Long,
    val wifiEnabled: Boolean,
    val online: Boolean,
    /** Inside the shop-closed window (see [QuietHours]). */
    val quiet: Boolean = false,
    /** The tablet has been carried (repeated motion) recently, so quiet hours do not excuse it. */
    val moved: Boolean = false,
    /** False when an administrator turned the protection off for this device: nothing ever escalates and any lockdown is cleared. */
    val enabled: Boolean = true,
)

data class GuardActions(
    val enableWifi: Boolean = false,
    val reconnect: Boolean = false,
    /** Look for open Wi-Fi networks and offer them to the system for connection. */
    val hunt: Boolean = false,
    /** Record the current location and network picture in the event log (uploaded on the next check-in). */
    val report: Boolean = false,
    val blockWanted: Boolean = false,
    val lockdownWanted: Boolean = false,
    val wentOnline: Boolean = false,
    val enteredLockdown: Boolean = false,
)

data class GuardStep(val state: GuardState, val actions: GuardActions)

/** Decides what the tablet must do this tick. Pure: no Android, so every rule is unit-tested. */
object ConnectivityPolicy {
    fun step(previous: GuardState, input: GuardInput): GuardStep {
        val now = input.now
        var st = previous

        // Protection switched off for this device: a clean, normal state, whatever the connection does.
        if (!input.enabled) return GuardStep(GuardState(), GuardActions())

        // Shop closed and the tablet is sitting still (its router is typically switched off): nothing escalates and no timer
        // runs, so the tablets are not blocked or locked by morning. A tablet that is being carried is still guarded.
        if (input.quiet && !input.moved) {
            st = st.copy(wifiOffSince = null, offlineSince = null, reconnectAttempts = 0, suspended = true)
            return GuardStep(st, GuardActions(lockdownWanted = st.lockdown))
        }
        // The quiet window just ended: switch Wi-Fi on straight away and count offline time from now, not from last night.
        if (st.suspended) st = st.copy(suspended = false, bootPending = true)

        // 1. The Wi-Fi radio.
        st = st.copy(wifiOffSince = if (input.wifiEnabled) null else (st.wifiOffSince ?: now))
        val offFor = st.wifiOffSince?.let { now - it } ?: 0L
        val enableWifi = !input.wifiEnabled &&
            (st.bootPending || offFor >= GuardTimings.WIFI_REENABLE_MS) &&
            now - st.lastEnableAt >= GuardTimings.ENABLE_RETRY_MS
        if (enableWifi) st = st.copy(lastEnableAt = now)
        st = st.copy(bootPending = false)

        // 2. Internet (a validated connection, not merely an attached network).
        val wentOnline = input.online && st.offlineSince != null
        st = st.copy(offlineSince = if (input.online) null else (st.offlineSince ?: now))
        if (input.online) st = st.copy(reconnectAttempts = 0)
        val offlineMs = st.offlineSince?.let { now - it } ?: 0L
        val offline = !input.online

        val reconnect = offline && input.wifiEnabled && now - st.lastReconnectAt >= GuardTimings.RECONNECT_EVERY_MS
        if (reconnect) st = st.copy(lastReconnectAt = now, reconnectAttempts = st.reconnectAttempts + 1)

        // 3. Escalation.
        val enteredLockdown = !st.lockdown && offline && offlineMs >= GuardTimings.LOCKDOWN_AFTER_MS
        if (enteredLockdown) st = st.copy(lockdown = true)
        val blockWanted = !st.lockdown && offline && offlineMs >= GuardTimings.BLOCK_AFTER_MS

        // 4. After 10 minutes with no network: hunt for any way out and keep reporting where the tablet is.
        val lost = offline && offlineMs >= GuardTimings.BLOCK_AFTER_MS
        val hunt = lost && now - st.lastHuntAt >= GuardTimings.HUNT_EVERY_MS
        if (hunt) st = st.copy(lastHuntAt = now)
        val report = lost && now - st.lastReportAt >= GuardTimings.REPORT_EVERY_MS
        if (report) st = st.copy(lastReportAt = now)

        return GuardStep(
            st,
            GuardActions(
                enableWifi = enableWifi, reconnect = reconnect, hunt = hunt, report = report,
                blockWanted = blockWanted, lockdownWanted = st.lockdown,
                wentOnline = wentOnline, enteredLockdown = enteredLockdown,
            ),
        )
    }
}
