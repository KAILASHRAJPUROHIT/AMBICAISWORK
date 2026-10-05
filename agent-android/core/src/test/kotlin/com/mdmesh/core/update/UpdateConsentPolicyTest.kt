package com.mdmesh.core.update

import com.mdmesh.core.update.UpdateConsentPolicy.DeferredAction
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class UpdateConsentPolicyTest {
    private val min = 60_000L
    private val hour = 60 * min

    @Test fun `only a device someone is using gets the popup`() {
        assertTrue(UpdateConsentPolicy.needsPopup(screenInteractive = true))
        assertFalse(UpdateConsentPolicy.needsPopup(screenInteractive = false))
    }

    @Test fun `the offer lasts sixty seconds`() {
        assertEquals(60, UpdateConsentPolicy.OFFER_SECONDS)
    }

    @Test fun `later is allowed for a day and then withdrawn`() {
        val first = 1_000_000L
        assertTrue(UpdateConsentPolicy.canDefer(first, first + 23 * hour))
        assertFalse(UpdateConsentPolicy.canDefer(first, first + 24 * hour))
        assertFalse(UpdateConsentPolicy.canDefer(first, first + 30 * hour))
    }

    @Test fun `a postponed update waits, then applies when the device is idle`() {
        val first = 0L
        val until = UpdateConsentPolicy.deferUntil(first)
        assertEquals(30 * min, until)
        // Before the time is up: wait, whatever the screen is doing.
        assertEquals(DeferredAction.WAIT, UpdateConsentPolicy.deferredAction(10 * min, until, first, screenInteractive = false))
        // Time is up and the screen is off: apply without a popup.
        assertEquals(DeferredAction.APPLY_NOW, UpdateConsentPolicy.deferredAction(31 * min, until, first, screenInteractive = false))
        // Time is up but someone is still using the device: keep waiting for an idle moment.
        assertEquals(DeferredAction.WAIT, UpdateConsentPolicy.deferredAction(31 * min, until, first, screenInteractive = true))
    }

    @Test fun `an overdue postponed update asks again once the device is in use`() {
        val first = 0L
        val until = UpdateConsentPolicy.deferUntil(first)
        assertEquals(DeferredAction.ASK_AGAIN, UpdateConsentPolicy.deferredAction(25 * hour, until, first, screenInteractive = true))
        assertEquals(DeferredAction.APPLY_NOW, UpdateConsentPolicy.deferredAction(25 * hour, until, first, screenInteractive = false))
    }

    @Test fun `a popup that never reported back is treated as unanswered`() {
        assertFalse(UpdateConsentPolicy.offerExpired(now = 62_000L, deadline = 60_000L))
        assertTrue(UpdateConsentPolicy.offerExpired(now = 66_000L, deadline = 60_000L))
    }
}
