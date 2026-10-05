package com.mdmesh.core.net

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class QuietHoursTest {
    private val min = 60_000L
    private val hour = 60 * min
    private fun m(h: Int, mm: Int = 0) = h * 60 + mm

    @Test fun `an overnight window wraps past midnight`() {
        val q = QuietHours.parse("22:00-08:00")!!
        assertTrue(q.contains(m(23)))
        assertTrue(q.contains(m(2)))
        assertTrue(q.contains(m(7, 59)))
        assertFalse(q.contains(m(8)))
        assertFalse(q.contains(m(12)))
        assertTrue(q.contains(m(22)))
    }

    @Test fun `a same-day window does not wrap`() {
        val q = QuietHours.parse("13:00-15:00")!!
        assertTrue(q.contains(m(14)))
        assertFalse(q.contains(m(16)))
        assertFalse(q.contains(m(2)))
    }

    @Test fun `no setting means the default, off disables, junk falls back to the default`() {
        assertEquals(QuietHours(m(22), m(8)), QuietHours.parse(null))
        assertEquals(QuietHours(m(22), m(8)), QuietHours.parse(""))
        assertEquals(QuietHours(m(22), m(8)), QuietHours.parse("nonsense"))
        assertNull(QuietHours.parse("off"))
        assertNull(QuietHours.parse("OFF"))
        assertNotNull(QuietHours.parse("21:30-07:15"))
    }

    @Test fun `a router off all night does not block or lock a tablet that stays put`() {
        var st = GuardState()
        val start = 0L
        var t = start
        // 9 hours of the shop being closed, offline the whole time, checked every 15 s.
        while (t < start + 9 * hour) {
            val step = ConnectivityPolicy.step(st, GuardInput(t, wifiEnabled = false, online = false, quiet = true, moved = false))
            st = step.state
            assertFalse("blocked at ${t / min} min", step.actions.blockWanted)
            assertFalse("locked at ${t / min} min", step.actions.lockdownWanted)
            assertFalse(step.actions.enableWifi)
            t += 15_000L
        }
        assertFalse(st.lockdown)
        assertNull(st.offlineSince)
    }

    @Test fun `when the shop opens wifi is switched on at once and the clock starts fresh`() {
        var st = GuardState()
        st = ConnectivityPolicy.step(st, GuardInput(0, wifiEnabled = false, online = false, quiet = true)).state
        // First tick after opening time, still no internet.
        val open = ConnectivityPolicy.step(st, GuardInput(9 * hour, wifiEnabled = false, online = false, quiet = false))
        assertTrue("wifi should be enabled immediately", open.actions.enableWifi)
        assertFalse(open.actions.blockWanted)
        // Nine minutes of morning outage is still fine, ten is not.
        var s = open.state
        var t = 9 * hour
        while (t < 9 * hour + 9 * min) {
            t += 15_000L
            s = ConnectivityPolicy.step(s, GuardInput(t, wifiEnabled = true, online = false)).state
        }
        assertFalse(ConnectivityPolicy.step(s, GuardInput(t, wifiEnabled = true, online = false)).actions.blockWanted)
        val later = ConnectivityPolicy.step(s, GuardInput(9 * hour + 11 * min, wifiEnabled = true, online = false))
        assertTrue(later.actions.blockWanted)
    }

    @Test fun `a tablet carried away at night is guarded as usual`() {
        var st = GuardState()
        var t = 0L
        var blocked = false
        var locked = false
        while (t < 40 * min) {
            val step = ConnectivityPolicy.step(st, GuardInput(t, wifiEnabled = true, online = false, quiet = true, moved = true))
            st = step.state
            blocked = blocked || step.actions.blockWanted
            locked = locked || step.actions.lockdownWanted
            t += 15_000L
        }
        assertTrue(blocked)
        assertTrue(locked)
    }

    @Test fun `a lockdown that already happened is not released by quiet hours`() {
        val st = GuardState(lockdown = true, offlineSince = 1L)
        val step = ConnectivityPolicy.step(st, GuardInput(10 * hour, wifiEnabled = false, online = false, quiet = true))
        assertTrue(step.actions.lockdownWanted)
    }

    @Test fun `repeated motion counts as carried, a single nudge does not`() {
        val t = 1_000_000L
        MotionState.record(t)
        assertFalse(MotionState.sustained(t + 1_000L))
        MotionState.record(t + 60_000L)
        assertTrue(MotionState.sustained(t + 90_000L))
        assertFalse(MotionState.sustained(t + 30 * min))
    }
}
