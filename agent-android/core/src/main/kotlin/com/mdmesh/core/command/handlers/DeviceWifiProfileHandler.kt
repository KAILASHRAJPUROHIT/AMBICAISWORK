package com.mdmesh.core.command.handlers

import android.content.Context
import android.net.wifi.WifiConfiguration
import android.net.wifi.WifiManager
import android.os.Build
import com.mdmesh.core.command.CommandHandler
import com.mdmesh.core.command.CommandResults
import com.mdmesh.proto.CommandEnvelope
import com.mdmesh.proto.CommandResult
import com.mdmesh.proto.DeviceAction
import com.mdmesh.proto.ProtocolJson
import kotlinx.serialization.Serializable

/**
 * `device.wifiProfile` — push a Wi-Fi network configuration so the device can join it
 * automatically. Distinct from the `wifi` toggle policy (radio enable/disable + lockdown);
 * this actually adds a saved network. Uses the legacy [WifiManager.addNetwork] API, which
 * (unlike for a regular app on API 29+) remains available to a Device Owner — the same
 * exemption the existing `wifi` policy strategies already rely on.
 */
class DeviceWifiProfileHandler(
    private val context: Context,
) : CommandHandler {

    override val type: String = DeviceAction.WIFI_PROFILE

    @Serializable
    private data class Payload(val ssid: String, val password: String? = null, val securityType: String = "wpa2")

    @Suppress("DEPRECATION")
    override suspend fun handle(command: CommandEnvelope): CommandResult {
        val payload = command.payload
            ?: return CommandResults.failed(command, "device.wifiProfile requires a payload")
        val parsed = runCatching {
            ProtocolJson.json.decodeFromJsonElement(Payload.serializer(), payload)
        }.getOrElse { return CommandResults.failed(command, "bad payload: ${it.message}") }

        return runCatching {
            val wifiManager = context.applicationContext
                .getSystemService(Context.WIFI_SERVICE) as WifiManager

            val config = WifiConfiguration().apply {
                SSID = "\"${parsed.ssid}\""
                when (parsed.securityType.lowercase()) {
                    "open" -> allowedKeyManagement.set(WifiConfiguration.KeyMgmt.NONE)
                    "wpa3" -> {
                        // KeyMgmt.SAE needs API 29+; below that, fall back to WPA2/PSK rather
                        // than referencing an API this device (and Android Lint, given
                        // minSdk 24) can't guarantee exists.
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                            allowedKeyManagement.set(WifiConfiguration.KeyMgmt.SAE)
                        } else {
                            allowedKeyManagement.set(WifiConfiguration.KeyMgmt.WPA_PSK)
                        }
                        preSharedKey = "\"${parsed.password.orEmpty()}\""
                    }
                    else -> {
                        allowedKeyManagement.set(WifiConfiguration.KeyMgmt.WPA_PSK)
                        preSharedKey = "\"${parsed.password.orEmpty()}\""
                    }
                }
            }

            val networkId = wifiManager.addNetwork(config)
            if (networkId == -1) {
                return CommandResults.failed(command, "addNetwork rejected the profile")
            }
            wifiManager.enableNetwork(networkId, false)
            wifiManager.saveConfiguration()
            CommandResults.done(command)
        }.getOrElse { CommandResults.failed(command, it.message ?: "wifiProfile failed") }
    }
}
