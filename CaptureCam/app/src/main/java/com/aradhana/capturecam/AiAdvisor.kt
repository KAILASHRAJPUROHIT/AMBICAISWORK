package com.aradhana.capturecam

import android.util.Base64
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Dns
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.net.InetAddress
import java.util.concurrent.TimeUnit

/**
 * Client for ai_advisor_server.py -- a standalone local-AI advisory proxy,
 * deliberately a SEPARATE process/port (7661) from capture_server.py
 * (7660). See that Python file's own docstring: capture_server.py must
 * stay zero-dependency on anything AI/engine-related (a past outage traced
 * to exactly that), so this talks to a dedicated proxy instead, never to
 * Ollama directly (which only binds 127.0.0.1 anyway) and never through
 * capture_server.py's own request path.
 *
 * Every call here is ADVISORY ONLY and must fail open: a null result means
 * "no opinion", not "no" -- callers must treat unreachable/timeout/unsure
 * exactly like "the AI had nothing useful to say" and fall back to
 * whatever the geometry-based gate already decided. This is a convenience
 * layer over gates that already work standalone, never a replacement.
 * Firsthand measured limitation (project memory, "Local AI can't verify
 * jewellery design"): qwen3-vl is NOT trustworthy for fine design-match
 * verification, only coarse "does this look roughly like X" questions --
 * every endpoint on the server side is scoped accordingly, on purpose.
 */
object AiAdvisor {
    private const val TAG = "AiAdvisor"
    private const val PORT = 7661

    private val client: OkHttpClient by lazy {
        OkHttpClient.Builder()
            // Same reuse-the-laptop's-current-IP reasoning as UploadClient's
            // Dns override (both processes run on the same machine) --
            // mDNS first, then the last-known-good IP a ServerDiscovery
            // sweep already found for capture_server.py, since that's the
            // same host this proxy runs on.
            .dns(object : Dns {
                override fun lookup(hostname: String): List<InetAddress> {
                    if (!hostname.equals("ARADHANA.local", ignoreCase = true)) {
                        return Dns.SYSTEM.lookup(hostname)
                    }
                    val discovered = UploadClient.discoveredServerIp?.let { ip ->
                        try { listOf(InetAddress.getByName(ip)) } catch (_: Exception) { emptyList() }
                    } ?: emptyList()
                    val resolved = try { Dns.SYSTEM.lookup(hostname) } catch (_: Exception) { emptyList() }
                    return (discovered + resolved).distinct().ifEmpty {
                        listOf("192.168.0.12").mapNotNull { ip ->
                            try { InetAddress.getByName(ip) } catch (_: Exception) { null }
                        }
                    }
                }
            })
            // Bounded well above the ~1-3s local-Ollama round trip measured
            // live, but still short enough that a stalled proxy can never
            // meaningfully stall the capture flow this is advisory to.
            .connectTimeout(3, TimeUnit.SECONDS)
            .writeTimeout(4, TimeUnit.SECONDS)
            .readTimeout(6, TimeUnit.SECONDS)
            .callTimeout(8, TimeUnit.SECONDS)
            .build()
    }

    private fun advisorUrl(serverUrl: String): String? = try {
        val uri = java.net.URI(serverUrl)
        "http://${uri.host}:$PORT"
    } catch (e: Exception) {
        Log.w(TAG, "advisorUrl parse failed for $serverUrl: ${e.message}")
        null
    }

    /** Coarse fallback for CategoryOrientation.looksWrongShape ONLY --
     * never for edge-clipping (a physical framing problem, not a
     * classification one) and never as the first-line check. Returns null
     * (no opinion) on any failure; callers must NOT treat null as either
     * yes or no. */
    suspend fun adviseShape(serverUrl: String, categoryLabel: String, jpeg: ByteArray): Boolean? =
        withContext(Dispatchers.IO) {
            val url = advisorUrl(serverUrl) ?: return@withContext null
            try {
                val imageB64 = Base64.encodeToString(jpeg, Base64.NO_WRAP)
                val body = JSONObject().apply {
                    put("image_b64", imageB64)
                    put("category_label", categoryLabel)
                }.toString().toRequestBody("application/json".toMediaType())
                val request = Request.Builder().url("$url/api/advise/shape").post(body).build()
                client.newCall(request).execute().use { response ->
                    val text = response.body?.string() ?: return@withContext null
                    val json = JSONObject(text)
                    if (!json.optBoolean("ok", false) || json.isNull("matches")) return@withContext null
                    json.getBoolean("matches")
                }
            } catch (e: Exception) {
                Log.w(TAG, "adviseShape failed: ${e.message}")
                null
            }
        }
}
