package com.mdmesh.core.battery

import com.mdmesh.core.battery.BatteryStage.NORMAL
import com.mdmesh.core.battery.BatteryStage.ORANGE
import com.mdmesh.core.battery.BatteryStage.RED
import com.mdmesh.core.battery.BatteryStage.YELLOW
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BatteryStageTest {
    @Test fun `stage boundaries match the agreed colours`() {
        assertEquals(NORMAL, BatteryStagePolicy.stageOf(100, false))
        assertEquals(NORMAL, BatteryStagePolicy.stageOf(31, false))
        assertEquals(YELLOW, BatteryStagePolicy.stageOf(30, false))
        assertEquals(YELLOW, BatteryStagePolicy.stageOf(21, false))
        assertEquals(ORANGE, BatteryStagePolicy.stageOf(20, false))
        assertEquals(ORANGE, BatteryStagePolicy.stageOf(11, false))
        assertEquals(RED, BatteryStagePolicy.stageOf(10, false))
        assertEquals(RED, BatteryStagePolicy.stageOf(1, false))
    }

    @Test fun `charging or an unknown level is always normal`() {
        assertEquals(NORMAL, BatteryStagePolicy.stageOf(5, true))
        assertEquals(NORMAL, BatteryStagePolicy.stageOf(-1, false))
    }

    @Test fun `a sound plays only when the stage gets worse`() {
        assertTrue(BatteryStagePolicy.shouldAnnounce(NORMAL, YELLOW))
        assertTrue(BatteryStagePolicy.shouldAnnounce(YELLOW, ORANGE))
        assertTrue(BatteryStagePolicy.shouldAnnounce(ORANGE, RED))
        assertTrue(BatteryStagePolicy.shouldAnnounce(NORMAL, RED)) // a big drop between readings still announces
        assertFalse(BatteryStagePolicy.shouldAnnounce(YELLOW, YELLOW))
        assertFalse(BatteryStagePolicy.shouldAnnounce(RED, ORANGE))
        assertFalse(BatteryStagePolicy.shouldAnnounce(ORANGE, NORMAL))
    }

    @Test fun `the first reading after a restart never plays a sound`() {
        assertFalse(BatteryStagePolicy.shouldAnnounce(null, RED))
        assertFalse(BatteryStagePolicy.shouldAnnounce(null, YELLOW))
    }

    @Test fun `red repeats every two minutes`() {
        assertEquals(120_000L, BatteryStagePolicy.RED_REPEAT_MS)
    }
}
