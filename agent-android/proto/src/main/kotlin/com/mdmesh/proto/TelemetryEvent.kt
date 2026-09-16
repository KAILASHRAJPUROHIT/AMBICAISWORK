package com.mdmesh.proto

import kotlinx.serialization.Serializable

/** A device lifecycle event, buffered offline and flushed to the server on the next check-in. */
@Serializable
data class TelemetryEventDto(
    val type: String,
    val ts: Long,
    val detail: String? = null,
)

/** Open registry of event types. */
object EventType {
    const val BOOT = "boot"
    const val APP_INSTALLED = "appInstalled"
    const val APP_UNINSTALLED = "appUninstalled"
    const val COMMAND_RESULT = "commandResult"
    const val CONNECTIVITY = "connectivityChange"
    const val CONNECTIVITY_LOST = "connectivityLost"
    const val CONNECTIVITY_RESTORED = "connectivityRestored"
    const val LOCATION_OFFLINE = "locationOffline"
    const val LOW_BATTERY = "lowBattery"
    const val ENROLLED = "enrolled"
}
