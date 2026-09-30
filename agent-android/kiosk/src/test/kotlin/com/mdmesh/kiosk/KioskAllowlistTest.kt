package com.mdmesh.kiosk

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class KioskAllowlistTest {
    private val own = "com.mdmesh.agent"

    @Test fun `always includes the agent and the Mi Doc Viewer`() {
        val r = KioskAllowlist.effective(listOf("com.android.chrome"), own)
        assertTrue(own in r)
        assertTrue("cn.wps.xiaomi.abroad.lite" in r)
        assertTrue("com.android.chrome" in r)
    }

    @Test fun `works when the console sends nothing`() {
        val r = KioskAllowlist.effective(emptyList(), own)
        assertEquals(setOf(own) + KioskAllowlist.ALWAYS_ALLOWED, r.toSet())
    }

    @Test fun `does not duplicate a package the console already listed`() {
        val r = KioskAllowlist.effective(listOf("cn.wps.xiaomi.abroad.lite", own, "a.b"), own)
        assertEquals(r.size, r.toSet().size)
        assertEquals(1, r.count { it == "cn.wps.xiaomi.abroad.lite" })
    }

    @Test fun `ignores blank entries`() {
        val r = KioskAllowlist.effective(listOf("", "  "), own)
        assertTrue(r.none { it.isBlank() })
    }
}
