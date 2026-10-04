package com.mdmesh.core.command.handlers

import android.content.Context
import com.mdmesh.core.command.CommandHandler
import com.mdmesh.core.command.CommandResults
import com.mdmesh.core.location.LocationCollector
import com.mdmesh.core.sync.CheckInWorker
import com.mdmesh.proto.CommandEnvelope
import com.mdmesh.proto.CommandResult
import com.mdmesh.proto.DeviceAction

/**
 * `device.locate` — take a fresh GPS/network fix right now ("Locate now"). The fix is returned in the command result
 * detail as `lat,lon ±accuracy m (provider)` and a check-in is queued so it also lands on the device's trail and map.
 */
class DeviceLocateHandler(
    private val collector: LocationCollector,
    private val context: Context,
) : CommandHandler {

    override val type: String = DeviceAction.LOCATE

    override suspend fun handle(command: CommandEnvelope): CommandResult = runCatching {
        val fix = collector.collectFresh()
            ?: return CommandResults.failed(
                command,
                "No location fix. Check that location services are on and the device is not deep indoors.",
            )
        // The command is handled inside a check-in; queue a follow-up one so the fix is reported to the trail/map.
        runCatching { CheckInWorker.scheduleNow(context) }
        val ageSec = ((System.currentTimeMillis() - fix.capturedAt) / 1000).coerceAtLeast(0)
        val acc = fix.accuracyM?.let { " ±${Math.round(it)} m" } ?: ""
        CommandResults.done(
            command,
            "%.5f,%.5f%s (%s, %ds old)".format(fix.lat, fix.lon, acc, fix.provider ?: "unknown", ageSec),
        )
    }.getOrElse { CommandResults.failed(command, it.message ?: "locate failed") }
}
