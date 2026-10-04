package com.mdmesh.core.net

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ConnectivityPolicyTest {
    private val min = 60_000L
    private val t0 = 1_000_000L

    private fun run(vararg steps: Triple<Long, Boolean, Boolean>, from: GuardState = GuardState()): Pair<GuardState, GuardActions> {
        var st = from
        var last = GuardActions()
        for ((now, wifi, online) in steps) {
            val r = ConnectivityPolicy.step(st, GuardInput(now, wifi, online))
            st = r.state; last = r.actions
        }
        return st to last
    }

    @Test fun wifiTurnedOffIsRestoredOnlyAfterThreeMinutes() {
        val (s1, a1) = run(Triple(t0, false, false))
        assertFalse(a1.enableWifi)
        val (_, a2) = run(Triple(t0 + 2 * min + 59_000, false, false), from = s1)
        assertFalse(a2.enableWifi)
        val (_, a3) = run(Triple(t0 + 3 * min, false, false), from = s1)
        assertTrue(a3.enableWifi)
    }

    @Test fun wifiIsSwitchedOnAtOnceAfterBoot() {
        val (_, a) = run(Triple(t0, false, false), from = GuardState(bootPending = true))
        assertTrue(a.enableWifi)
    }

    @Test fun bootFlagIsUsedUpByTheFirstTick() {
        val (s, _) = run(Triple(t0, true, true), from = GuardState(bootPending = true))
        assertFalse(s.bootPending)
    }

    @Test fun enableIsNotRepeatedEveryTick() {
        val (s1, a1) = run(Triple(t0, false, false), from = GuardState(bootPending = true))
        assertTrue(a1.enableWifi)
        val (_, a2) = run(Triple(t0 + 15_000, false, false), from = s1)
        assertFalse(a2.enableWifi)
    }

    @Test fun noScreenBeforeTenMinutesOffline() {
        val (s, _) = run(Triple(t0, true, false))
        val (_, a) = run(Triple(t0 + 10 * min - 1, true, false), from = s)
        assertFalse(a.blockWanted)
        assertFalse(a.hunt)
        assertFalse(a.report)
    }

    @Test fun tenMinutesOfflineShowsTheBlockScreenAndStartsHuntingAndReporting() {
        val (s, _) = run(Triple(t0, true, false))
        val (_, a) = run(Triple(t0 + 10 * min, true, false), from = s)
        assertTrue(a.blockWanted)
        assertFalse(a.lockdownWanted)
        assertTrue(a.hunt)
        assertTrue(a.report)
    }

    @Test fun huntingAndReportingKeepTheirOwnRhythm() {
        var st = run(Triple(t0, true, false)).first
        var hunts = 0; var reports = 0
        var now = t0 + 10 * min
        repeat(20) { // 5 minutes in 15 s ticks
            val r = ConnectivityPolicy.step(st, GuardInput(now, true, false))
            st = r.state
            if (r.actions.hunt) hunts++
            if (r.actions.report) reports++
            now += 15_000
        }
        assertEquals(5, hunts)    // once a minute
        assertEquals(3, reports)  // every two minutes: at 0, 2 and 4 minutes
    }

    @Test fun thirtyMinutesOfflineLocksDownForGood() {
        val (s, _) = run(Triple(t0, true, false))
        val (s2, a) = run(Triple(t0 + 30 * min, true, false), from = s)
        assertTrue(a.enteredLockdown)
        assertTrue(a.lockdownWanted)
        assertFalse(a.blockWanted)
        assertTrue(s2.lockdown)
    }

    @Test fun lockdownSurvivesTheInternetComingBack() {
        val locked = GuardState(lockdown = true)
        val (s, a) = run(Triple(t0, true, true), from = locked)
        assertTrue(a.lockdownWanted)
        assertTrue(s.lockdown)
    }

    @Test fun lockdownIsShownAtOnceAfterARebootEvenIfOnline() {
        val (_, a) = run(Triple(t0, true, true), from = GuardState(lockdown = true, bootPending = true))
        assertTrue(a.lockdownWanted)
    }

    @Test fun comingBackOnlineClearsTheBlockScreenAndReportsIt() {
        val (s, _) = run(Triple(t0, true, false))
        val (s2, a1) = run(Triple(t0 + 12 * min, true, false), from = s)
        assertTrue(a1.blockWanted)
        val (_, a2) = run(Triple(t0 + 13 * min, true, true), from = s2)
        assertFalse(a2.blockWanted)
        assertTrue(a2.wentOnline)
    }

    @Test fun reconnectIsTriedEveryTwentySecondsWhileOffline() {
        var st = GuardState()
        var tries = 0
        var now = t0
        repeat(12) { // 3 minutes of 15 s ticks
            val r = ConnectivityPolicy.step(st, GuardInput(now, true, false))
            st = r.state
            if (r.actions.reconnect) tries++
            now += 15_000
        }
        assertEquals(6, tries) // 15 s ticks, one attempt per 20 s window = every second tick (0, 30, 60, 90, 120, 150 s)
    }

    @Test fun wifiOffTimeCountsAsOfflineTimeToo() {
        val (s, _) = run(Triple(t0, false, false))
        val (_, a) = run(Triple(t0 + 10 * min, false, false), from = s)
        assertTrue(a.blockWanted)
    }
}
