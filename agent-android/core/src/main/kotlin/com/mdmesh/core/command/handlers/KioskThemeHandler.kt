package com.mdmesh.core.command.handlers

import com.mdmesh.core.command.CommandHandler
import com.mdmesh.core.command.CommandResults
import com.mdmesh.core.store.KioskStateStore
import com.mdmesh.proto.CommandEnvelope
import com.mdmesh.proto.CommandResult
import com.mdmesh.proto.DeviceAction
import com.mdmesh.proto.KioskThemePayload
import com.mdmesh.proto.ProtocolJson

/**
 * `device.kioskTheme` — restyle the currently-active kiosk (status bar/exit chrome colours)
 * without a full kiosk.enter round-trip (no app-picker/exit-mode/password churn). Merges each
 * non-null field into the persisted [com.mdmesh.proto.KioskApplyPayload.theme] and re-saves it;
 * [KioskStateStore]'s reactive `flow()` — the same path `kiosk.enter`/`kiosk.exit` already use —
 * carries the change to the on-screen launcher immediately. A no-op (not a failure) when no
 * kiosk is currently active, since there's no on-screen theme to restyle.
 */
class KioskThemeHandler(
    private val store: KioskStateStore,
) : CommandHandler {

    override val type: String = DeviceAction.KIOSK_THEME

    override suspend fun handle(command: CommandEnvelope): CommandResult {
        val patch = command.payload?.let {
            runCatching { ProtocolJson.json.decodeFromJsonElement(KioskThemePayload.serializer(), it) }
                .getOrElse { e -> return CommandResults.failed(command, "bad payload: ${e.message}") }
        } ?: KioskThemePayload()

        val current = store.load() ?: return CommandResults.done(command, "no active kiosk to restyle")
        val theme = current.theme.copy(
            backgroundColor = patch.backgroundColor ?: current.theme.backgroundColor,
            textColor = patch.textColor ?: current.theme.textColor,
            accentColor = patch.accentColor ?: current.theme.accentColor,
        )
        store.save(current.copy(theme = theme))
        return CommandResults.done(command)
    }
}
