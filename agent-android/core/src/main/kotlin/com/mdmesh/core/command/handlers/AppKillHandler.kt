package com.mdmesh.core.command.handlers

import android.content.Context
import com.mdmesh.core.command.CommandHandler
import com.mdmesh.core.command.CommandResults
import com.mdmesh.policy.wifi.DpmHandle
import com.mdmesh.proto.CommandEnvelope
import com.mdmesh.proto.CommandResult
import com.mdmesh.proto.DeviceAction
import com.mdmesh.proto.ProtocolJson
import kotlinx.serialization.Serializable

/**
 * `device.appKill` — force-stop a single runaway/misbehaving app on the device, right now,
 * without touching enrollment or Device Owner status.
 *
 * Uses [android.app.admin.DevicePolicyManager.setPackagesSuspended] as the kill primitive: a
 * regular Device Owner app has no public API for a true `forceStopPackage` (that's a
 * system/signature permission, not grantable to us) — but suspending a package immediately stops
 * its running process, same practical effect for "kill this app now". Un-suspending right after
 * leaves the app killed but freely launchable again afterward, instead of permanently blocked —
 * this is a kill, not a ban.
 *
 * HARD SELF-PROTECTION (non-negotiable): this must never be able to suspend/kill the agent's own
 * package. Suspending a Device Owner app would very likely leave the device unmanageable — no
 * further commands could arrive to undo it, and recovery could require a physical factory reset.
 * The guard below checks the target against the agent's own package name unconditionally, before
 * any DPM call, regardless of what the server/console ever sends.
 */
class AppKillHandler(
    @param:dagger.hilt.android.qualifiers.ApplicationContext private val context: Context,
    private val handle: DpmHandle,
) : CommandHandler {

    override val type: String = DeviceAction.APP_KILL

    @Serializable
    private data class Payload(val packageName: String)

    override suspend fun handle(command: CommandEnvelope): CommandResult {
        val payload = command.payload
            ?: return CommandResults.failed(command, "device.appKill requires a payload")
        val parsed = runCatching {
            ProtocolJson.json.decodeFromJsonElement(Payload.serializer(), payload)
        }.getOrElse { return CommandResults.failed(command, "bad payload: ${it.message}") }

        val target = parsed.packageName.trim()
        if (target.isEmpty()) {
            return CommandResults.failed(command, "packageName is blank")
        }
        // Non-negotiable: never allow the agent to suspend/kill itself, under any name variant
        // the server might send (exact match only -- no prefix/contains cleverness that could
        // itself be tricked either way).
        if (target == context.packageName) {
            return CommandResults.failed(
                command,
                "refused: target package is the MDM agent itself ($target) -- never killable",
            )
        }

        return runCatching {
            val packages = arrayOf(target)
            val notSuspended = handle.dpm.setPackagesSuspended(handle.admin, packages, true)
            if (target in notSuspended) {
                return@runCatching CommandResults.failed(
                    command,
                    "could not suspend $target (not installed, or a protected system package)",
                )
            }
            // Un-suspend immediately: the goal is "kill it now", not "block it forever". The
            // suspend->unsuspend pulse has already done its job by the time this line runs --
            // the target process is stopped.
            runCatching { handle.dpm.setPackagesSuspended(handle.admin, packages, false) }
            CommandResults.done(command, "killed $target")
        }.getOrElse { CommandResults.failed(command, it.message ?: "appKill failed") }
    }
}
