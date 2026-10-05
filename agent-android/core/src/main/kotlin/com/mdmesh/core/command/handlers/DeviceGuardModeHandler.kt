package com.mdmesh.core.command.handlers

import android.content.Context
import com.mdmesh.core.command.CommandHandler
import com.mdmesh.core.command.CommandResults
import com.mdmesh.core.net.GuardSwitch
import com.mdmesh.core.net.LockdownReleaser
import com.mdmesh.proto.CommandEnvelope
import com.mdmesh.proto.CommandResult
import com.mdmesh.proto.DeviceAction
import com.mdmesh.proto.ProtocolJson
import kotlinx.serialization.Serializable

/**
 * `device.guardMode` { "enabled": true|false } - turns the offline protection off (or back on) for this device only.
 * Turning it off also lifts any lockdown or full-screen message at once, so the device goes back to normal and stays that way
 * however long it is without internet.
 */
class DeviceGuardModeHandler(
    private val context: Context,
    private val releaser: LockdownReleaser,
) : CommandHandler {

    override val type: String = DeviceAction.GUARD_MODE

    @Serializable
    private data class Payload(val enabled: Boolean)

    override suspend fun handle(command: CommandEnvelope): CommandResult = runCatching {
        val p = command.payload?.let { ProtocolJson.json.decodeFromJsonElement(Payload.serializer(), it) }
            ?: return CommandResults.failed(command, "device.guardMode requires { enabled }")
        GuardSwitch.set(context, p.enabled)
        if (!p.enabled) releaser.release("offline protection turned off from the console")
        CommandResults.done(command, if (p.enabled) "offline protection on" else "offline protection off; lockdown cleared")
    }.getOrElse { CommandResults.failed(command, it.message ?: "guard mode failed") }
}
