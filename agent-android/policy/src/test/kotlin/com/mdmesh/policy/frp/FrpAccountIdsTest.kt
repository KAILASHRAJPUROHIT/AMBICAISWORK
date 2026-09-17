package com.mdmesh.policy.frp

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class FrpAccountIdsTest {
    @Test fun acceptsNumericIds() {
        assertEquals(listOf("123456789012345678901", "234567890123456789012"),
            FrpAccountIds.parse("123456789012345678901,234567890123456789012"))
    }
    @Test fun rejectsUnsafeConfiguration() {
        listOf("", " ", "info@aradhanajewellers.com", "people/123", "0", "123,", "123,123", "123, 456", "123\n").forEach {
            assertThrows(IllegalArgumentException::class.java) { FrpAccountIds.parse(it) }
        }
    }
}
