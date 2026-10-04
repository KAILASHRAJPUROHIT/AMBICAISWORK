package com.mdmesh.core.command.handlers

import com.mdmesh.core.command.CommandHandler
import com.mdmesh.core.command.CommandResults
import com.mdmesh.core.net.LockdownReleaser
import com.mdmesh.proto.CommandEnvelope
import com.mdmesh.proto.CommandResult

/**
 * `device.lockdownRelease` - an administrator lifts the offline lockdown from the console. Only a tablet that has
 * got online again (an administrator connected it to Wi-Fi) can receive it; the emailed-code route on the tablet is the
 * other way out.
 */
class DeviceLockdownReleaseHandler(private val releaser: LockdownReleaser) : CommandHandler {
    override val type: String = "device.lockdownRelease"

    override suspend fun handle(command: CommandEnvelope): CommandResult =
        runCatching {
            releaser.release("console")
            CommandResults.done(command, "lockdown released")
        }.getOrElse { CommandResults.failed(command, it.message ?: "release failed") }
}
