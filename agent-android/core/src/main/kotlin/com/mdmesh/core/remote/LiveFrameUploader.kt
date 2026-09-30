package com.mdmesh.core.remote

import com.mdmesh.core.config.ServerConfigStore
import com.mdmesh.core.store.DeviceIdentity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import javax.inject.Inject
import javax.inject.Singleton

/** Pushes a batch of live-view H.264 packets to `/public/agent/v1/remote/live` (relayed in memory, never stored). */
@Singleton
class LiveFrameUploader @Inject constructor(
    private val httpClient: OkHttpClient,
    private val serverConfig: ServerConfigStore,
    private val identity: DeviceIdentity,
) {
    private val jpeg = "application/octet-stream".toMediaTypeOrNull()

    suspend fun upload(kind: String, bytes: ByteArray): Boolean = withContext(Dispatchers.IO) {
        val deviceId = identity.current() ?: return@withContext false
        val secret = identity.secret() ?: return@withContext false
        val request = Request.Builder()
            .url("${serverConfig.baseUrl()}/rest/public/agent/v1/remote/live")
            .addHeader("Authorization", "Bearer $secret")
            .addHeader("X-Device-Number", deviceId)
            .addHeader("X-Live-Kind", kind)
            .post(bytes.toRequestBody(jpeg))
            .build()
        runCatching { httpClient.newCall(request).execute().use { it.isSuccessful } }.getOrDefault(false)
    }
}
