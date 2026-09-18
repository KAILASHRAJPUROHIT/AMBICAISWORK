package com.mdmesh.core.remote

import com.mdmesh.core.config.ServerConfigStore
import com.mdmesh.core.store.DeviceIdentity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import javax.inject.Inject
import javax.inject.Singleton

/** Uploads one remote-view capture to `/public/agent/v1/remote/snapshot` — device-authenticated
 *  (the same bearer secret as checkin), not an admin session; see `RemoteSnapshotUploadResource`
 *  server-side. Each upload overwrites the device's previous capture of that [kind]; there's no
 *  history, only "the latest." */
@Singleton
class RemoteSnapshotUploader @Inject constructor(
    private val httpClient: OkHttpClient,
    private val serverConfig: ServerConfigStore,
    private val identity: DeviceIdentity,
) {
    suspend fun upload(kind: String, contentType: String, bytes: ByteArray): Boolean = withContext(Dispatchers.IO) {
        val deviceId = identity.current() ?: return@withContext false
        val secret = identity.secret() ?: return@withContext false

        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("deviceNumber", deviceId)
            .addFormDataPart("kind", kind)
            .addFormDataPart("contentType", contentType)
            .addFormDataPart("file", "$kind.bin", bytes.toRequestBody(contentType.toMediaTypeOrNull()))
            .build()

        val request = Request.Builder()
            .url("${serverConfig.baseUrl()}/rest/public/agent/v1/remote/snapshot")
            .addHeader("Authorization", "Bearer $secret")
            .post(body)
            .build()

        runCatching {
            httpClient.newCall(request).execute().use { it.isSuccessful }
        }.getOrDefault(false)
    }
}
