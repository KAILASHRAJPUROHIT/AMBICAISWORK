package com.aradhanajewellers.smsrelay

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SenderWhitelistTest {
    @Test fun exactAndPrefixPatternsAreSupported() {
        val allowed = listOf("VM-ICICIB", "AD-HDFCBK", "AX-*")
        assertTrue(matchesApprovedSender("VM-ICICIB", allowed))
        assertTrue(matchesApprovedSender("AX-HDFCBK", allowed))
        assertFalse(matchesApprovedSender("VK-PERSONAL", allowed))
        assertFalse(matchesApprovedSender("VM-ICICIB-FAKE", allowed))
    }
}
