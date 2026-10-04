package com.mdmesh.agent.net

import com.mdmesh.core.config.ServerConfigStore
import com.mdmesh.core.store.DeviceIdentity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

/** Asks the server to email the unlock code, and checks the code the administrator types. */
@Singleton
class LockdownApi @Inject constructor(
    private val http: OkHttpClient,
    private val serverConfig: ServerConfigStore,
    private val identity: DeviceIdentity,
) {
    data class Result(val ok: Boolean, val message: String, val sentTo: String = "")

    suspend fun requestCode(): Result = post("unlock-request", null)
    suspend fun verify(code: String): Result = post("unlock-verify", code)

    private suspend fun post(path: String, code: String?): Result = withContext(Dispatchers.IO) {
        val id = identity.current() ?: return@withContext Result(false, "This tablet is not enrolled.")
        val secret = identity.secret() ?: return@withContext Result(false, "This tablet is not enrolled.")
        val json = JSONObject().apply { if (code != null) put("code", code) }.toString()
        val request = Request.Builder()
            .url("${serverConfig.baseUrl()}/rest/public/agent/v1/lockdown/$path")
            .addHeader("Authorization", "Bearer $secret")
            .addHeader("X-Device-Number", id)
            .post(json.toRequestBody("application/json".toMediaTypeOrNull()))
            .build()
        try {
            http.newCall(request).execute().use { r ->
                val text = r.body?.string().orEmpty()
                val body = runCatching { JSONObject(text) }.getOrNull()
                    ?: return@use Result(false, "The server did not answer properly (HTTP ${r.code}).")
                if (body.optString("status") == "OK") {
                    val data = body.optJSONObject("data")
                    Result(true, "OK", data?.optString("sentTo").orEmpty())
                } else {
                    Result(false, friendly(body.optString("message")))
                }
            }
        } catch (e: IOException) {
            Result(false, "No connection to the server. Connect the tablet to Wi-Fi first.")
        }
    }

    private fun friendly(code: String): String = when (code) {
        "error.unlock.mail.unconfigured" -> "The server cannot send email yet. Ask the administrator to use Release lockdown in the console."
        "error.unlock.mail.failed" -> "The code could not be emailed. Try again in a minute."
        "error.unlock.rate.limited" -> "Too many codes requested. Wait ten minutes and try again."
        "error.unlock.invalid" -> "That code is wrong or has expired."
        else -> code.ifBlank { "The request was refused." }
    }
}
