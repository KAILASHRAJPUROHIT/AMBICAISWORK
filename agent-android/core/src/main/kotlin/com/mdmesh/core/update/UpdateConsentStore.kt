package com.mdmesh.core.update

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/** The agent-update request waiting on the person using the device, persisted so it survives the app being restarted. */
@Singleton
class UpdateConsentStore @Inject constructor(@ApplicationContext context: Context) {
    private val prefs = context.getSharedPreferences("update_consent", Context.MODE_PRIVATE)

    enum class State { NONE, WAITING, DEFERRED, INSTALLING }

    data class Pending(
        val commandId: String,
        /** The original `app.install` payload (JSON text). */
        val payload: String,
        val state: State,
        val firstOfferedAt: Long,
        val offerDeadline: Long,
        val deferUntil: Long,
        val deferCount: Int,
        /** True once "Update later" is no longer allowed. */
        val mandatory: Boolean,
        /** The agent's version code when the update was requested, to tell afterwards whether it applied. */
        val versionBefore: Long,
        val targetVersion: Long,
    )

    @Synchronized
    fun get(): Pending? {
        val id = prefs.getString(K_ID, null) ?: return null
        val state = runCatching { State.valueOf(prefs.getString(K_STATE, "NONE")!!) }.getOrDefault(State.NONE)
        if (state == State.NONE) return null
        return Pending(
            commandId = id,
            payload = prefs.getString(K_PAYLOAD, "") ?: "",
            state = state,
            firstOfferedAt = prefs.getLong(K_FIRST, 0),
            offerDeadline = prefs.getLong(K_DEADLINE, 0),
            deferUntil = prefs.getLong(K_DEFER_UNTIL, 0),
            deferCount = prefs.getInt(K_DEFER_COUNT, 0),
            mandatory = prefs.getBoolean(K_MANDATORY, false),
            versionBefore = prefs.getLong(K_BEFORE, 0),
            targetVersion = prefs.getLong(K_TARGET, 0),
        )
    }

    @Synchronized
    fun put(p: Pending) {
        prefs.edit()
            .putString(K_ID, p.commandId).putString(K_PAYLOAD, p.payload).putString(K_STATE, p.state.name)
            .putLong(K_FIRST, p.firstOfferedAt).putLong(K_DEADLINE, p.offerDeadline).putLong(K_DEFER_UNTIL, p.deferUntil)
            .putInt(K_DEFER_COUNT, p.deferCount).putBoolean(K_MANDATORY, p.mandatory)
            .putLong(K_BEFORE, p.versionBefore).putLong(K_TARGET, p.targetVersion)
            .apply()
    }

    @Synchronized
    fun clear() { prefs.edit().clear().apply() }

    private companion object {
        const val K_ID = "id"; const val K_PAYLOAD = "payload"; const val K_STATE = "state"
        const val K_FIRST = "first"; const val K_DEADLINE = "deadline"; const val K_DEFER_UNTIL = "deferUntil"
        const val K_DEFER_COUNT = "deferCount"; const val K_MANDATORY = "mandatory"
        const val K_BEFORE = "before"; const val K_TARGET = "target"
    }
}
