package com.mdmesh.core.command.handlers

import com.mdmesh.core.command.CommandHandler
import com.mdmesh.core.command.CommandResults
import com.mdmesh.core.remote.RemoteCaptureController
import com.mdmesh.proto.CommandEnvelope
import com.mdmesh.proto.CommandResult
import com.mdmesh.proto.DeviceAction

/** Stops the current remote snapshot session immediately. */
class RemoteSessionStopHandler(
    private val controller: RemoteCaptureController,
) : CommandHandler {
    override val type: String = DeviceAction.REMOTE_SESSION_STOP

    override suspend fun handle(command: CommandEnvelope): CommandResult {
        controller.stop()
        return CommandResults.done(command, "remote capture session stopped")
    }
}
