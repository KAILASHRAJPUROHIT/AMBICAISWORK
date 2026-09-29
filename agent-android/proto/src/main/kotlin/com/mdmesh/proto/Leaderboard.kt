package com.mdmesh.proto

import kotlinx.serialization.Serializable

/**
 * The shop's live sales leaderboard as the server serves it to a tablet
 * (`GET rest/public/agent/v1/leaderboard`). The whole document is small (a handful of
 * salespeople) and is replaced wholesale on every poll.
 */
@Serializable
data class LeaderboardResponse(
    /** When the server received the snapshot (epoch ms) - drives the "updated" / stale readout. */
    val receivedAt: Long = 0,
    val board: LeaderboardBoard = LeaderboardBoard(),
)

@Serializable
data class LeaderboardBoard(
    /** Shop business date, `yyyy-MM-dd`, from the ledger server's own clock. */
    val businessDate: String = "",
    val generatedAt: String = "",
    val entries: List<LeaderboardEntry> = emptyList(),
    val totals: LeaderboardTotals = LeaderboardTotals(),
)

@Serializable
data class LeaderboardEntry(
    val name: String,
    val bills: Int = 0,
    val total: Double = 0.0,
    val rank: Int = 0,
)

@Serializable
data class LeaderboardTotals(
    val salesmen: Int = 0,
    val bills: Long = 0,
    val amount: Double = 0.0,
)
