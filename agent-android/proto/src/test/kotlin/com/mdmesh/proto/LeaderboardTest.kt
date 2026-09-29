package com.mdmesh.proto

import org.junit.Assert.assertEquals
import org.junit.Test

class LeaderboardTest {
    private val json =
        """{"receivedAt":1790662828192,"board":{"businessDate":"2026-09-29","generatedAt":"x","entries":[""" +
            """{"name":"HITESH KUMAR","bills":3,"total":147879.0,"rank":1},""" +
            """{"name":"MANISH MALI","bills":1,"total":13680.0,"rank":2}],""" +
            """"totals":{"salesmen":2,"bills":4,"amount":161559.0}}}"""

    @Test
    fun decodesServerShape() {
        val r = ProtocolJson.json.decodeFromString(LeaderboardResponse.serializer(), json)
        assertEquals(1790662828192L, r.receivedAt)
        assertEquals("2026-09-29", r.board.businessDate)
        assertEquals(2, r.board.entries.size)
        assertEquals("HITESH KUMAR", r.board.entries[0].name)
        assertEquals(147879.0, r.board.entries[0].total, 0.001)
        assertEquals(4L, r.board.totals.bills)
    }

    @Test
    fun roundTripsThroughTheCache() {
        val r = ProtocolJson.json.decodeFromString(LeaderboardResponse.serializer(), json)
        val again = ProtocolJson.json.decodeFromString(
            LeaderboardResponse.serializer(),
            ProtocolJson.json.encodeToString(LeaderboardResponse.serializer(), r),
        )
        assertEquals(r, again)
    }
}
