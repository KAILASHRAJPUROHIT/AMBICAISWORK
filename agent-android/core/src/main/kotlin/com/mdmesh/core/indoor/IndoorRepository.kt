package com.mdmesh.core.indoor

import android.content.Context
import com.mdmesh.core.net.MdmApi
import com.mdmesh.core.store.DeviceIdentity
import com.mdmesh.proto.IndoorBundleDto
import com.mdmesh.proto.IndoorSurveyRequest
import com.mdmesh.proto.ProtocolJson
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import javax.inject.Inject
import javax.inject.Singleton

/** Downloads the store's plan + survey (cached for offline use) and uploads survey readings. */
@Singleton
class IndoorRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    private val api: MdmApi,
    private val identity: DeviceIdentity,
) {
    private val prefs get() = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    /** Last good bundle from the server, or null if this device has none (no plan set up, or never fetched). */
    fun cached(): IndoorBundleDto? = prefs.getString(KEY_JSON, null)?.let {
        runCatching { ProtocolJson.json.decodeFromString(IndoorBundleDto.serializer(), it) }.getOrNull()
    }

    /**
     * Fetches the bundle. Returns the fresh bundle, or null when the server has no plan. On a network or server error
     * the cached copy is returned instead, so positioning keeps working through an outage.
     */
    suspend fun refresh(): IndoorBundleDto? = withContext(Dispatchers.IO) {
        val id = identity.current()?.takeIf { it.isNotBlank() } ?: return@withContext cached()
        val secret = identity.secret()?.takeIf { it.isNotBlank() } ?: return@withContext cached()
        runCatching {
            val r = api.indoorBundle("Bearer $secret", id)
            if (!r.isOk) return@runCatching cached()
            val data = r.data
            val e = prefs.edit()
            if (data == null) e.remove(KEY_JSON) else {
                e.putString(KEY_JSON, ProtocolJson.json.encodeToString(IndoorBundleDto.serializer(), data))
            }
            e.apply()
            data
        }.getOrElse { cached() }
    }

    /** Uploads one surveyed point. Returns null on success or the reason it failed. */
    suspend fun uploadSurvey(x: Double, y: Double, rssi: Map<String, Int>, mag: Double?): String? =
        withContext(Dispatchers.IO) {
            val id = identity.current()?.takeIf { it.isNotBlank() } ?: return@withContext "device is not enrolled"
            val secret = identity.secret()?.takeIf { it.isNotBlank() } ?: return@withContext "device is not enrolled"
            runCatching {
                val r = api.indoorSurvey("Bearer $secret", IndoorSurveyRequest(id, x, y, rssi, mag))
                if (r.isOk) null else (r.message ?: "the server rejected the survey point")
            }.getOrElse { it.message ?: "upload failed" }
        }

    private companion object {
        const val PREFS = "indoor_bundle"
        const val KEY_JSON = "json"
    }
}
