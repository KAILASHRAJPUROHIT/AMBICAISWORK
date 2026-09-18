package com.mdmesh.core.command.handlers

import com.mdmesh.core.command.CommandHandler
import com.mdmesh.core.command.CommandResults
import com.mdmesh.core.remote.RemoteCaptureController
import com.mdmesh.proto.CommandEnvelope
import com.mdmesh.proto.CommandResult
import com.mdmesh.proto.DeviceAction
import com.mdmesh.proto.ProtocolJson
import com.mdmesh.proto.RemoteSessionStartPayload

/** Starts one bounded remote snapshot session. The app service owns capture and upload. */
class RemoteSessionStartHandler(
    private val controller: RemoteCaptureController,
) : CommandHandler {
    override val type: String = DeviceAction.REMOTE_SESSION_START

    override suspend fun handle(command: CommandEnvelope): CommandResult {
        val payload = command.payload ?: return CommandResults.failed(command, "remote session requires a payload")
        val session = runCatching {
            ProtocolJson.json.decodeFromJsonElement(RemoteSessionStartPayload.serializer(), payload)
        }.getOrElse { return CommandResults.failed(command, "bad remote session payload: ${it.message}") }
        if (session.sessionId.isBlank() || session.kinds.none { it in KINDS }) {
            return CommandResults.failed(command, "remote session has no supported capture kind")
        }
        return if (controller.start(session.copy(kinds = session.kinds.filter { it in KINDS }.distinct()))) {
            CommandResults.accepted(command, "remote capture session started")
        } else {
            CommandResults.failed(command, "remote capture service could not start")
        }
    }

    private companion object {
        val KINDS = setOf("screen", "cameraFront", "cameraBack", "mic")
    }
}
