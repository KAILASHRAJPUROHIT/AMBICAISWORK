package com.mdmesh.proto

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonObject

/**
 * Which sections of the kiosk are shown, as set by the admin in the console (Settings > Kiosk
 * sections). Everything is ON unless the server says `false`, so an old server, an empty value or
 * garbage never hides anything. The admin menu is deliberately not a section and can never be hidden.
 */
data class KioskSections(
    val leaderboard: Boolean = true,
    val quickControls: Boolean = true,
    val clientLogo: Boolean = true,
    val clockCard: Boolean = true,
    val statusPills: Boolean = true,
) {
    companion object {
        val ALL_ON = KioskSections()

        /** Parses `{"leaderboard":false,...}`; unknown keys and non-boolean values are ignored. */
        fun parse(json: String?): KioskSections {
            if (json.isNullOrBlank()) return ALL_ON
            val o: JsonObject = runCatching { ProtocolJson.json.parseToJsonElement(json).jsonObject }.getOrNull()
                ?: return ALL_ON
            fun on(key: String): Boolean = (o[key] as? JsonPrimitive)?.booleanOrNull ?: true
            return KioskSections(
                leaderboard = on("leaderboard"),
                quickControls = on("quickControls"),
                clientLogo = on("clientLogo"),
                clockCard = on("clockCard"),
                statusPills = on("statusPills"),
            )
        }
    }
}
