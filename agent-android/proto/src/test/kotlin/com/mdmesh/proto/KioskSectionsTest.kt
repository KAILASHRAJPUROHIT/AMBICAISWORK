package com.mdmesh.proto

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class KioskSectionsTest {
    @Test fun nullBlankAndGarbageMeanEverythingOn() {
        assertEquals(KioskSections.ALL_ON, KioskSections.parse(null))
        assertEquals(KioskSections.ALL_ON, KioskSections.parse(""))
        assertEquals(KioskSections.ALL_ON, KioskSections.parse("not json"))
        assertEquals(KioskSections.ALL_ON, KioskSections.parse("[1,2]"))
    }

    @Test fun onlyExplicitFalseHidesASection() {
        val s = KioskSections.parse("""{"leaderboard":false,"quickControls":"no","bogus":false}""")
        assertFalse(s.leaderboard)
        assertTrue(s.quickControls)          // a non-boolean value never hides anything
        assertTrue(s.clientLogo && s.clockCard && s.statusPills)
    }

    @Test fun eachSectionParses() {
        val s = KioskSections.parse("""{"leaderboard":false,"quickControls":false,"clientLogo":false,"clockCard":false,"statusPills":false}""")
        assertFalse(s.leaderboard || s.quickControls || s.clientLogo || s.clockCard || s.statusPills)
    }
}
