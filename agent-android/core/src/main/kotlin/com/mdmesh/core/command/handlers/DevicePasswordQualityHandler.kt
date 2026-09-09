package com.mdmesh.core.command.handlers

import android.app.admin.DevicePolicyManager
import com.mdmesh.core.command.CommandHandler
import com.mdmesh.core.command.CommandResults
import com.mdmesh.policy.wifi.DpmHandle
import com.mdmesh.proto.CommandEnvelope
import com.mdmesh.proto.CommandResult
import com.mdmesh.proto.DeviceAction
import com.mdmesh.proto.ProtocolJson
import kotlinx.serialization.Serializable

/**
 * `device.passwordQuality` — enforce a minimum lock-screen passcode quality/length via
 * [android.app.admin.DevicePolicyManager.setPasswordQuality] +
 * [android.app.admin.DevicePolicyManager.setPasswordMinimumLength]. `quality = "none"` clears
 * the requirement (minLength is ignored in that case).
 */
class DevicePasswordQualityHandler(
    private val handle: DpmHandle,
) : CommandHandler {

    override val type: String = DeviceAction.PASSWORD_QUALITY

    @Serializable
    private data class Payload(val quality: String, val minLength: Int = 0)

    @Suppress("DEPRECATION") // setPasswordQuality/setPasswordMinimumLength deprecated API 29+ in
    // favor of PasswordPolicy, but remain the correct Device-Owner API at this project's minSdk 24.
    override suspend fun handle(command: CommandEnvelope): CommandResult {
        val payload = command.payload
            ?: return CommandResults.failed(command, "device.passwordQuality requires a payload")
        val parsed = runCatching {
            ProtocolJson.json.decodeFromJsonElement(Payload.serializer(), payload)
        }.getOrElse { return CommandResults.failed(command, "bad payload: ${it.message}") }

        val quality = QUALITY_MAP[parsed.quality]
            ?: return CommandResults.failed(command, "unknown quality: ${parsed.quality}")

        return runCatching {
            handle.dpm.setPasswordQuality(handle.admin, quality)
            if (quality != DevicePolicyManager.PASSWORD_QUALITY_UNSPECIFIED && parsed.minLength > 0) {
                handle.dpm.setPasswordMinimumLength(handle.admin, parsed.minLength)
            }
            CommandResults.done(command)
        }.getOrElse { CommandResults.failed(command, it.message ?: "passwordQuality failed") }
    }

    private companion object {
        val QUALITY_MAP = mapOf(
            "none" to DevicePolicyManager.PASSWORD_QUALITY_UNSPECIFIED,
            "numeric" to DevicePolicyManager.PASSWORD_QUALITY_NUMERIC,
            "alphabetic" to DevicePolicyManager.PASSWORD_QUALITY_ALPHABETIC,
            "alphanumeric" to DevicePolicyManager.PASSWORD_QUALITY_ALPHANUMERIC,
            "complex" to DevicePolicyManager.PASSWORD_QUALITY_COMPLEX,
        )
    }
}
