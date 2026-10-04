package com.mdmesh.core.command.handlers

import com.mdmesh.core.command.CommandHandler
import com.mdmesh.core.command.CommandResults
import com.mdmesh.core.indoor.IndoorEngine
import com.mdmesh.proto.CommandEnvelope
import com.mdmesh.proto.CommandResult
import com.mdmesh.proto.DeviceAction
import com.mdmesh.proto.ProtocolJson
import kotlinx.serialization.Serializable

/** `device.indoorLocate` — estimate the in-store position right now from Wi-Fi and report it in the result. */
class DeviceIndoorLocateHandler(private val engine: IndoorEngine) : CommandHandler {

    override val type: String = DeviceAction.INDOOR_LOCATE

    override suspend fun handle(command: CommandEnvelope): CommandResult = runCatching {
        if (!engine.reload() && !engine.hasMap()) {
            return CommandResults.failed(command, "No store floor plan is set up yet. Create one under Indoor map in the console.")
        }
        val fix = engine.locateNow()
            ?: return CommandResults.failed(command, "Could not work out a position. Check that Wi-Fi and location are on.")
        val zone = fix.zone?.let { " in $it" } ?: ""
        CommandResults.done(command, "%.1f, %.1f m%s (±%.1f m)".format(fix.x, fix.y, zone, fix.spreadM))
    }.getOrElse { CommandResults.failed(command, it.message ?: "indoor locate failed") }
}

/**
 * `device.indoorSurvey` — record a survey point at the plan position the admin tapped in the console. The device stands
 * where it is, averages a few Wi-Fi scans and uploads them.
 */
class DeviceIndoorSurveyHandler(private val engine: IndoorEngine) : CommandHandler {

    override val type: String = DeviceAction.INDOOR_SURVEY

    @Serializable
    private data class Payload(val x: Double, val y: Double, val samples: Int = 3)

    override suspend fun handle(command: CommandEnvelope): CommandResult = runCatching {
        val p = command.payload?.let { ProtocolJson.json.decodeFromJsonElement(Payload.serializer(), it) }
            ?: return CommandResults.failed(command, "device.indoorSurvey requires { x, y }")
        val err = engine.survey(p.x, p.y, p.samples)
        if (err == null) {
            CommandResults.done(command, "recorded at %.1f, %.1f m".format(p.x, p.y))
        } else {
            CommandResults.failed(command, err)
        }
    }.getOrElse { CommandResults.failed(command, it.message ?: "survey failed") }
}
