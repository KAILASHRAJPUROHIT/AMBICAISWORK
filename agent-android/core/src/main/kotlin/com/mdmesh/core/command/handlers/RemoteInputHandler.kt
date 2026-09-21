package com.mdmesh.core.command.handlers

import com.mdmesh.core.command.CommandHandler
import com.mdmesh.core.command.CommandResults
import com.mdmesh.core.remote.ScreenCaptureAccessibilityService
import com.mdmesh.proto.CommandEnvelope
import com.mdmesh.proto.CommandResult
import com.mdmesh.proto.DeviceAction
import com.mdmesh.proto.ProtocolJson
import com.mdmesh.proto.RemoteInputPayload

/** Replays remote touch/swipe or global navigation key via AccessibilityService. */
class RemoteInputHandler : CommandHandler {
    override val type: String = DeviceAction.REMOTE_INPUT

    override suspend fun handle(command: CommandEnvelope): CommandResult {
        val payload = command.payload ?: return CommandResults.failed(command, "remote input requires a payload")
        val p = runCatching {
            ProtocolJson.json.decodeFromJsonElement(RemoteInputPayload.serializer(), payload)
        }.getOrElse { return CommandResults.failed(command, "bad remote input payload: ${it.message}") }

        if (!ScreenCaptureAccessibilityService.isConnected()) {
            return CommandResults.failed(command, "AccessibilityService not enabled on device")
        }

        val x = p.x
        val y = p.y
        val endX = p.endX
        val endY = p.endY
        val key = p.key

        val success = when (p.action.lowercase()) {
            "tap" -> {
                if (x == null || y == null) false
                else ScreenCaptureAccessibilityService.injectTap(x, y)
            }
            "swipe" -> {
                if (x == null || y == null || endX == null || endY == null) false
                else ScreenCaptureAccessibilityService.injectSwipe(
                    x, y, endX, endY, p.durationMs ?: 300L
                )
            }
            "key" -> {
                if (key == null) false
                else ScreenCaptureAccessibilityService.injectKey(key)
            }
            "text" -> {
                val textToInject = p.text
                if (textToInject == null) false
                else ScreenCaptureAccessibilityService.injectText(textToInject)
            }
            else -> false
        }

        return if (success) {
            CommandResults.done(command, "input dispatched")
        } else {
            CommandResults.failed(command, "gesture injection failed")
        }
    }
}
