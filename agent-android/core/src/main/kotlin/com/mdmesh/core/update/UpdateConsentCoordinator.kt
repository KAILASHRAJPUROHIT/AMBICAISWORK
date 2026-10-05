package com.mdmesh.core.update

import android.content.Context
import android.content.Intent
import android.os.PowerManager
import android.util.Log
import com.mdmesh.core.command.handlers.AppInstallPayload
import com.mdmesh.core.install.InstallManager
import com.mdmesh.core.install.InstallOutcome
import com.mdmesh.core.sync.PendingResults
import com.mdmesh.core.telemetry.EventLog
import com.mdmesh.core.update.UpdateConsentStore.State
import com.mdmesh.proto.CommandResult
import com.mdmesh.proto.CommandStatus
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Two-way consent for agent self-updates. Updating the agent restarts the app, so when someone is using the device the
 * update is first offered in a 60-second popup (English over Hindi): **Update now** or **Update later**.
 *
 * Flow, for an `app.install` of the agent's own package (manual from the console or from the automatic rollout):
 *  - screen off -> nobody to ask, install straight away (the caller proceeds as before);
 *  - screen on  -> the request is stored, the popup opens, and the command is acknowledged `accepted` ("waiting for the user");
 *      - Update now / no answer in 60 s -> install;
 *      - Update later -> the server is told (`accepted`, "deferred ...", plus an `updateDeferred` event), and the update is
 *        applied by [tick] once the device is idle (screen off) at least [UpdateConsentPolicy.DEFER_MINUTES] later. After
 *        [UpdateConsentPolicy.MAX_DEFER_HOURS] the popup returns without a "later" button.
 *  - After the restart [reportAfterRestart] reports the final `done` (or `failed`) for the original command.
 */
@Singleton
class UpdateConsentCoordinator @Inject constructor(
    @ApplicationContext private val context: Context,
    private val store: UpdateConsentStore,
    private val installManager: InstallManager,
    private val pending: PendingResults,
    private val events: EventLog,
) {
    enum class Choice { NOW, LATER, TIMEOUT }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    /**
     * Called by the install handler for the agent's own package. Returns the acknowledgement to send when the request was
     * parked for the user, or null when the caller should install right now.
     */
    fun interceptSelfInstall(commandId: String, payload: JsonElement, versionCode: Long?): CommandResult? {
        if (!UpdateConsentPolicy.needsPopup(isInteractive())) {
            store.put(newPending(commandId, payload.toString(), versionCode, State.INSTALLING, mandatory = false))
            return null
        }
        val now = System.currentTimeMillis()
        val existing = store.get()
        val first = if (existing != null && existing.state != State.INSTALLING) existing.firstOfferedAt else now
        val mandatory = !UpdateConsentPolicy.canDefer(first, now)
        store.put(
            newPending(commandId, payload.toString(), versionCode, State.WAITING, mandatory)
                .copy(firstOfferedAt = first, offerDeadline = now + UpdateConsentPolicy.OFFER_SECONDS * 1000L,
                    deferCount = existing?.deferCount ?: 0),
        )
        openPopup()
        events.record("updateOffered", "agent update offered to the user (${UpdateConsentPolicy.OFFER_SECONDS}s)")
        return result(commandId, CommandStatus.ACCEPTED,
            "waiting for the user: update popup shown for ${UpdateConsentPolicy.OFFER_SECONDS} seconds")
    }

    /** The install handler finished an inline install without restarting (skipped or failed): nothing left to report later. */
    fun finishInline() { store.clear() }

    /** The person's answer from the popup. */
    fun onChoice(choice: Choice) {
        val p = store.get() ?: return
        if (p.state != State.WAITING) return
        val now = System.currentTimeMillis()
        if (choice == Choice.LATER && !p.mandatory && UpdateConsentPolicy.canDefer(p.firstOfferedAt, now)) {
            store.put(p.copy(state = State.DEFERRED, deferUntil = UpdateConsentPolicy.deferUntil(now), deferCount = p.deferCount + 1))
            pending.add(listOf(result(p.commandId, CommandStatus.ACCEPTED,
                "update deferred by the user; it will apply when the device is idle (about ${UpdateConsentPolicy.DEFER_MINUTES} minutes or later)")))
            events.record("updateDeferred", "user chose Update later (deferral #${p.deferCount + 1})")
            return
        }
        events.record(if (choice == Choice.NOW) "updateAccepted" else "updateAutoStarted",
            if (choice == Choice.NOW) "user chose Update now" else "no answer in ${UpdateConsentPolicy.OFFER_SECONDS}s: updating")
        install(p)
    }

    /** Called about once a minute by the service: applies postponed updates and recovers lost popups. */
    fun tick() {
        val p = store.get() ?: return
        val now = System.currentTimeMillis()
        when (p.state) {
            State.WAITING -> if (UpdateConsentPolicy.offerExpired(now, p.offerDeadline)) {
                // The popup never reported back (it was killed or could not open): same as no answer.
                events.record("updateAutoStarted", "popup unanswered: updating")
                install(p)
            }
            State.DEFERRED -> when (UpdateConsentPolicy.deferredAction(now, p.deferUntil, p.firstOfferedAt, isInteractive())) {
                UpdateConsentPolicy.DeferredAction.APPLY_NOW -> {
                    events.record("updateAutoStarted", "device idle: applying the postponed update")
                    install(p)
                }
                UpdateConsentPolicy.DeferredAction.ASK_AGAIN -> {
                    store.put(p.copy(state = State.WAITING, mandatory = true,
                        offerDeadline = now + UpdateConsentPolicy.OFFER_SECONDS * 1000L))
                    openPopup()
                }
                UpdateConsentPolicy.DeferredAction.WAIT -> Unit
            }
            State.INSTALLING -> if (now - p.offerDeadline > STUCK_INSTALL_MS && now - p.firstOfferedAt > STUCK_INSTALL_MS) {
                // An install that neither finished nor restarted the app: give up so the server can retry.
                pending.add(listOf(result(p.commandId, CommandStatus.FAILED, "update did not finish")))
                store.clear()
            }
            State.NONE -> Unit
        }
    }

    /** Reports the outcome of an update that restarted the app. Call once at service start. */
    fun reportAfterRestart() {
        val p = store.get() ?: return
        if (p.state != State.INSTALLING) return
        val now = installedVersion()
        if (p.targetVersion > 0 && now >= p.targetVersion || p.targetVersion == 0L && now > p.versionBefore) {
            pending.add(listOf(result(p.commandId, CommandStatus.DONE, "updated to version code $now")))
            events.record("updateApplied", "agent updated to version code $now")
            store.clear()
        } else if (System.currentTimeMillis() - p.offerDeadline > STUCK_INSTALL_MS) {
            pending.add(listOf(result(p.commandId, CommandStatus.FAILED, "update did not apply (still version code $now)")))
            store.clear()
        }
    }

    // --- internals ------------------------------------------------------------------------------------------------

    private fun install(p: UpdateConsentStore.Pending) {
        store.put(p.copy(state = State.INSTALLING, offerDeadline = System.currentTimeMillis()))
        scope.launch {
            val outcome = runCatching {
                val payload = kotlinx.serialization.json.Json.parseToJsonElement(p.payload)
                installManager.install(AppInstallPayload.toRequest(payload))
            }.getOrElse { InstallOutcome.Failure(null, it.message ?: "install error") }
            when (outcome) {
                // A self-update normally kills this process before we get here; [reportAfterRestart] reports it.
                InstallOutcome.Success -> Log.i(TAG, "agent update installed")
                is InstallOutcome.Skipped -> {
                    pending.add(listOf(result(p.commandId, CommandStatus.DONE, "skipped: ${outcome.reason}")))
                    store.clear()
                }
                is InstallOutcome.Failure -> {
                    pending.add(listOf(result(p.commandId, CommandStatus.FAILED, outcome.reason)))
                    store.clear()
                }
            }
        }
    }

    private fun newPending(id: String, payload: String, versionCode: Long?, state: State, mandatory: Boolean) =
        UpdateConsentStore.Pending(
            commandId = id, payload = payload, state = state,
            firstOfferedAt = System.currentTimeMillis(), offerDeadline = System.currentTimeMillis(),
            deferUntil = 0, deferCount = 0, mandatory = mandatory,
            versionBefore = installedVersion(), targetVersion = versionCode ?: 0,
        )

    private fun openPopup() {
        runCatching {
            context.startActivity(
                Intent().setClassName(context.packageName, POPUP_ACTIVITY)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            )
        }.onFailure { Log.w(TAG, "could not open the update popup", it) }
    }

    private fun isInteractive(): Boolean =
        (context.getSystemService(Context.POWER_SERVICE) as? PowerManager)?.isInteractive ?: true

    private fun installedVersion(): Long = runCatching {
        @Suppress("DEPRECATION")
        context.packageManager.getPackageInfo(context.packageName, 0).let {
            if (android.os.Build.VERSION.SDK_INT >= 28) it.longVersionCode else it.versionCode.toLong()
        }
    }.getOrDefault(0L)

    private fun result(commandId: String, status: CommandStatus, detail: String) =
        CommandResult(commandId = commandId, status = status, detail = detail, completedAt = Instant.now().toString())

    private companion object {
        const val TAG = "UpdateConsent"
        const val POPUP_ACTIVITY = "com.mdmesh.agent.update.UpdateConsentActivity"
        const val STUCK_INSTALL_MS = 15 * 60_000L
    }
}
