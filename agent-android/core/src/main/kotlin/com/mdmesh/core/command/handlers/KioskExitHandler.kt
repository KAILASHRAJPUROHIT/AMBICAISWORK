package com.mdmesh.core.command.handlers

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import com.mdmesh.core.command.CommandHandler
import com.mdmesh.core.command.CommandResults
import com.mdmesh.core.store.KioskStateStore
import com.mdmesh.kiosk.KioskController
import com.mdmesh.kiosk.KioskResult
import com.mdmesh.proto.CommandEnvelope
import com.mdmesh.proto.CommandResult

/**
 * `kiosk.exit` — release COSU lock-task (clear allowlist + persistent-HOME claim). On success the
 * persisted [KioskStateStore] payload is cleared so the agent does not re-enter kiosk on next boot,
 * and the AMBIC MDM status/settings screen is opened after lock task releases.
 */
class KioskExitHandler(
    private val kiosk: KioskController,
    private val store: KioskStateStore,
    private val homeComponent: ComponentName,
    private val context: Context,
) : CommandHandler {

    override val type: String = "kiosk.exit"

    override suspend fun handle(command: CommandEnvelope): CommandResult =
        when (val r = kiosk.exit()) {
            KioskResult.Ok -> {
                store.save(null)
                // Drop the kiosk-only HOME claim, then open the agent status screen. This keeps
                // management settings available immediately after a local or remote kiosk exit.
                disableHomeAlias()
                openAgentHome()
                CommandResults.done(command)
            }
            KioskResult.Unsupported -> CommandResults.unsupported(command, "kiosk unsupported on this device")
            is KioskResult.Failed -> CommandResults.failed(command, r.reason)
        }

    private fun disableHomeAlias() {
        runCatching {
            context.packageManager.setComponentEnabledSetting(
                homeComponent,
                PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
                PackageManager.DONT_KILL_APP,
            )
        }
    }

    private fun openAgentHome() {
        runCatching {
            context.startActivity(
                Intent().setClassName(context.packageName, "com.mdmesh.agent.MainActivity")
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        }
    }
}
