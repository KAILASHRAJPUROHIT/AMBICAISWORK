package com.mdmesh.policy.frp

/** Syntax validation only: account ownership and recoverability require acceptance testing. */
object FrpAccountIds {
    fun parse(value: String): List<String> {
        require(value.isNotBlank()) { "FRP blocked: verified numeric Google recovery account IDs are not configured" }
        val ids = value.split(",")
        require(ids.all { it.matches(Regex("[1-9][0-9]{0,29}")) }) {
            "FRP blocked: use numeric Google user IDs from People API, not email addresses"
        }
        require(ids.distinct().size == ids.size) { "FRP blocked: duplicate recovery account IDs" }
        return ids
    }
}
