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

    @Test fun bankTransactionClassifierCatchesKnownAndUnknownBanks() {
        assertTrue(isBankTransactionMessage("VM-ICICIB", "Rs 1,250.00 credited to A/c XX1234 via UPI Ref 123", emptyList()))
        assertTrue(isBankTransactionMessage("UNKNOWN", "INR 500 debited from account XX1234. UTR 123456", emptyList()))
        assertTrue(isBankTransactionMessage("UNKNOWN", "Your account XX1234 has been credited amount 500. UTR 123456", emptyList()))
        assertTrue(isBankTransactionMessage("SENDER", "Rs 900 spent", listOf("SENDER")))
    }

    @Test fun bankTransactionClassifierRejectsOtpAndPersonalMessages() {
        assertFalse(isBankTransactionMessage("VK-APP", "Your OTP is 123456. Do not share it.", emptyList()))
        assertFalse(isBankTransactionMessage("PERSONAL", "I paid Rs 500 for dinner yesterday", emptyList()))
        assertFalse(isBankTransactionMessage("PROMO", "Get Rs 500 cashback on your next purchase", emptyList()))
    }
}
