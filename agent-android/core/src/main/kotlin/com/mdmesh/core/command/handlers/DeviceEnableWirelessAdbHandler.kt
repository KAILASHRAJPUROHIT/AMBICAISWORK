package com.mdmesh.core.command.handlers

import android.os.Build
import com.mdmesh.core.command.CommandHandler
import com.mdmesh.core.command.CommandResults
import com.mdmesh.policy.wifi.DpmHandle
import com.mdmesh.policy.wifi.WirelessAdbEnabler
import com.mdmesh.proto.CommandEnvelope
import com.mdmesh.proto.CommandResult

/**
 * `device.enableWirelessAdb` — turns on the wireless-debugging listener for the fleet's
 * one-time `WRITE_SETTINGS` appop rollout (see [AutoRotationSettingsPolicy]/
 * `provision-aosp-device.ps1`), without an ADB moment or a per-device Settings visit.
 *
 * `ADB_WIFI_ENABLED` and `ADB_ENABLED` are both confirmed on
 * `DevicePolicyManagerService.GLOBAL_SETTINGS_ALLOWLIST` (AOSP master) -- unlike
 * `AIRPLANE_MODE_ON` (see [FlightModeSettingsPolicy]'s retraction), this one is real: Device
 * Owner can flip it via `setGlobalSetting` and it throws nothing.
 *
 * This closes only the first half of the "reach an already-enrolled QR device" problem:
 * - **Address**: already solved. `DynamicState.ipAddress` (`DynamicStateCollector`) reports the
 *   device's current LAN IP on every check-in, so once this command lands the operator already
 *   knows where to point `adb`.
 * - **Port**: NOT solved here, and can't honestly be claimed as solved. Modern wireless
 *   debugging (Android 11+) advertises an ephemeral TLS port via mDNS
 *   (`_adb-tls-connect._tcp`), not a fixed one -- no public API lets an app read that port back
 *   out to report it. The operator's machine still needs to be on the same LAN and run
 *   `adb pair`/`adb mdns services` (or a plain `adb connect <ip>:5555` on older OEM builds that
 *   still default to the legacy fixed port) to find it.
 * - **First-trust handshake**: also NOT verified either way. Whether the very first connection
 *   from a new operator machine needs an on-device tap is an adbd-level question that has not
 *   been checked against source the way the two settings above were -- flag this to whoever
 *   runs the rollout rather than assume it's silent.
 *
 * Net effect: this removes the "must physically visit every device" requirement for turning the
 * listener on (one push reaches the whole fleet via the existing command-dispatch path), and
 * leaves a genuinely per-device, but no-visit-required, `adb connect` step for the operator.
 */
class DeviceEnableWirelessAdbHandler(
    private val handle: DpmHandle,
) : CommandHandler {

    override val type: String = "device.enableWirelessAdb"

    override suspend fun handle(command: CommandEnvelope): CommandResult {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            return CommandResults.unsupported(command, "wireless debugging requires API 30+")
        }
        if (!handle.dpm.isDeviceOwnerApp(handle.admin.packageName)) {
            return CommandResults.unsupported(command, "enableWirelessAdb requires Device Owner")
        }
        return if (WirelessAdbEnabler.tryEnable(handle)) {
            CommandResults.done(command, "wireless debugging listener enabled; pair/connect over the LAN")
        } else {
            CommandResults.failed(command, "enableWirelessAdb failed")
        }
    }
}
