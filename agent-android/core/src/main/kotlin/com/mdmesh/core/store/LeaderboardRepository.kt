package com.mdmesh.core.store

import android.content.Context
import android.content.SharedPreferences
import com.mdmesh.core.net.MdmApi
import com.mdmesh.proto.LeaderboardResponse
import com.mdmesh.proto.ProtocolJson
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Fetches the shop's live sales leaderboard and caches the last good copy, so the kiosk card
 * survives a brief network drop (shown with an "updated N min ago" note rather than vanishing).
 *
 * The kiosk home polls [refresh] every 30 seconds while it is on screen. That is deliberately
 * NOT the normal MDM check-in: check-ins are push-triggered and far too infrequent for a live
 * board, and this call is a few hundred bytes.
 */
@Singleton
class LeaderboardRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    private val api: MdmApi,
    private val identity: DeviceIdentity,
) {
    /** Fetches and caches; returns false when the device is not enrolled or the call failed. The
     *  cached copy is only replaced by a successful response. */
    suspend fun refresh(): Boolean = withContext(Dispatchers.IO) {
        val id = identity.current()?.takeIf { it.isNotBlank() } ?: return@withContext false
        val secret = identity.secret()?.takeIf { it.isNotBlank() } ?: return@withContext false
        runCatching {
            val r = api.leaderboard("Bearer $secret", id)
            if (!r.isOk) return@runCatching false
            val e = prefs(context).edit()
            val data = r.data
            if (data == null) {
                e.remove(KEY_JSON)               // shop has never pushed one: hide the card
            } else {
                e.putString(KEY_JSON, ProtocolJson.json.encodeToString(LeaderboardResponse.serializer(), data))
            }
            e.putLong(KEY_VERSION, System.currentTimeMillis()).apply()
            true
        }.getOrDefault(false)
    }

    companion object {
        const val PREFS = "leaderboard"
        const val KEY_VERSION = "version"
        private const val KEY_JSON = "json"

        fun prefs(context: Context): SharedPreferences = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

        /** Last good leaderboard, or null if none has ever been received. */
        fun read(context: Context): LeaderboardResponse? =
            prefs(context).getString(KEY_JSON, null)?.let {
                runCatching { ProtocolJson.json.decodeFromString(LeaderboardResponse.serializer(), it) }.getOrNull()
            }
    }
}
