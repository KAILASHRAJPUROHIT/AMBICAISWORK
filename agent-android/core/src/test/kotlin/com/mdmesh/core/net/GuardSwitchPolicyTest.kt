package com.mdmesh.core.net

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class GuardSwitchPolicyTest {
    private val min = 60_000L

    @Test fun `with the protection off a tablet never blocks or locks however long it is offline`() {
        var st = GuardState()
        var t = 0L
        while (t < 6 * 60 * min) {
            val step = ConnectivityPolicy.step(st, GuardInput(t, wifiEnabled = false, online = false, enabled = false))
            st = step.state
            assertFalse(step.actions.blockWanted)
            assertFalse(step.actions.lockdownWanted)
            assertFalse(step.actions.enableWifi)
            t += 15_000L
        }
        assertFalse(st.lockdown)
        assertNull(st.offlineSince)
    }

    @Test fun `switching the protection off clears a lockdown that was already active`() {
        val locked = GuardState(lockdown = true, offlineSince = 1L)
        val step = ConnectivityPolicy.step(locked, GuardInput(10 * min, wifiEnabled = false, online = false, enabled = false))
        assertFalse(step.actions.lockdownWanted)
        assertFalse(step.state.lockdown)
    }

    @Test fun `switching it back on starts the clocks from scratch`() {
        val off = ConnectivityPolicy.step(GuardState(lockdown = true), GuardInput(0, true, false, enabled = false)).state
        val on = ConnectivityPolicy.step(off, GuardInput(60 * min, wifiEnabled = true, online = false, enabled = true))
        assertFalse("not blocked the moment it is turned on", on.actions.blockWanted)
        assertTrue(on.state.offlineSince != null)
        val later = ConnectivityPolicy.step(on.state, GuardInput(75 * min, wifiEnabled = true, online = false, enabled = true))
        assertTrue(later.actions.blockWanted)
        assertEquals(false, later.actions.lockdownWanted)
    }
}
