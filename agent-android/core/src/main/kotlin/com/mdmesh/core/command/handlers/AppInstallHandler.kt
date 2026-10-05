package com.mdmesh.core.command.handlers

import com.mdmesh.core.command.CommandHandler
import com.mdmesh.core.command.CommandResults
import com.mdmesh.core.install.InstallManager
import com.mdmesh.core.install.InstallOutcome
import com.mdmesh.proto.CommandEnvelope
import com.mdmesh.proto.CommandResult

/**
 * `app.install` — silently install (or upgrade) an app as Device Owner. Payload:
 * `{ url, packageName, versionCode?, sha256?, runAfterInstall?, parts? }`. A `parts` list
 * (`[{url, sha256?}]`) installs a split-APK bundle (base + splits) in one session; without it
 * the single `url`/`localPath` is used. Version gating, downgrade-blocking, and the install
 * itself are delegated to [InstallManager].
 */
class AppInstallHandler(
    private val installManager: InstallManager,
    private val ownPackage: String? = null,
    private val consent: com.mdmesh.core.update.UpdateConsentCoordinator? = null,
) : CommandHandler {

    override val type: String = "app.install"

    override suspend fun handle(command: CommandEnvelope): CommandResult {
        val payload = command.payload
            ?: return CommandResults.failed(command, "app.install requires a payload")
        val request = runCatching { AppInstallPayload.toRequest(payload) }
            .getOrElse { return CommandResults.failed(command, "bad payload: ${it.message}") }

        // The agent updating ITSELF restarts the app: ask the person using the device first (see UpdateConsentCoordinator).
        val selfUpdate = consent != null && ownPackage != null && request.packageName == ownPackage
        if (selfUpdate) {
            val parked = consent!!.interceptSelfInstall(command.commandId, payload, request.versionCode)
            if (parked != null) return parked
        }

        val outcome = installManager.install(request)
        if (selfUpdate && outcome !is InstallOutcome.Success) consent!!.finishInline()
        return when (outcome) {
            InstallOutcome.Success -> CommandResults.done(command)
            is InstallOutcome.Skipped -> CommandResults.done(command, "skipped: ${outcome.reason}")
            is InstallOutcome.Failure -> CommandResults.failed(command, outcome.reason)
        }
    }
}

/** The `app.install` payload, shared with the update-consent flow that replays a postponed install. */
object AppInstallPayload {
    @kotlinx.serialization.Serializable
    private data class PartPayload(val url: String? = null, val localPath: String? = null, val sha256: String? = null)

    @kotlinx.serialization.Serializable
    private data class Payload(
        val url: String? = null,
        val localPath: String? = null,
        val packageName: String,
        val versionCode: Long? = null,
        val sha256: String? = null,
        val runAfterInstall: Boolean = false,
        val parts: List<PartPayload> = emptyList(),
    )

    fun toRequest(payload: kotlinx.serialization.json.JsonElement): com.mdmesh.core.install.InstallRequest {
        val p = com.mdmesh.proto.ProtocolJson.json.decodeFromJsonElement(Payload.serializer(), payload)
        return com.mdmesh.core.install.InstallRequest(
            url = p.url,
            localPath = p.localPath,
            packageName = p.packageName,
            versionCode = p.versionCode,
            sha256 = p.sha256,
            runAfterInstall = p.runAfterInstall,
            parts = p.parts.map { com.mdmesh.core.install.ApkPart(url = it.url, localPath = it.localPath, sha256 = it.sha256) },
        )
    }
}
