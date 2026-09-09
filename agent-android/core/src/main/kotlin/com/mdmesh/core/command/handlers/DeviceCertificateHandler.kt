package com.mdmesh.core.command.handlers

import android.util.Base64
import com.mdmesh.core.command.CommandHandler
import com.mdmesh.core.command.CommandResults
import com.mdmesh.policy.wifi.DpmHandle
import com.mdmesh.proto.CommandEnvelope
import com.mdmesh.proto.CommandResult
import com.mdmesh.proto.DeviceAction
import com.mdmesh.proto.ProtocolJson
import kotlinx.serialization.Serializable

/**
 * `device.certificate` — install a CA certificate via
 * [android.app.admin.DevicePolicyManager.installCaCert]. The certificate is identified by its
 * own DER bytes (there is no separate alias in this DPM API), so removal (not implemented here;
 * add `device.certificateRemove` if/when needed) must resend the same bytes to
 * `uninstallCaCert`.
 */
class DeviceCertificateHandler(
    private val handle: DpmHandle,
) : CommandHandler {

    override val type: String = DeviceAction.CERTIFICATE

    @Serializable
    private data class Payload(val certBase64: String)

    override suspend fun handle(command: CommandEnvelope): CommandResult {
        val payload = command.payload
            ?: return CommandResults.failed(command, "device.certificate requires a payload")
        val parsed = runCatching {
            ProtocolJson.json.decodeFromJsonElement(Payload.serializer(), payload)
        }.getOrElse { return CommandResults.failed(command, "bad payload: ${it.message}") }

        val certBytes = runCatching {
            Base64.decode(parsed.certBase64, Base64.DEFAULT)
        }.getOrElse { return CommandResults.failed(command, "certBase64 is not valid base64") }

        return runCatching {
            val installed = handle.dpm.installCaCert(handle.admin, certBytes)
            if (installed) {
                CommandResults.done(command)
            } else {
                CommandResults.failed(command, "installCaCert rejected the certificate")
            }
        }.getOrElse { CommandResults.failed(command, it.message ?: "certificate install failed") }
    }
}
