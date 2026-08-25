package com.aradhana.capturecam

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.Dns
import org.json.JSONObject
import java.net.InetAddress
import java.security.SecureRandom
import java.security.cert.X509Certificate
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager
import java.util.concurrent.TimeUnit
import java.io.File

/**
 * Talks to capture_server.py's existing /api/capture/save -- the SAME
 * endpoint and multipart contract capture.html's browser flow already
 * uses (category/tag_code/staff_name form fields + jewel/tag file parts),
 * so this app needs no server-side changes at all.
 *
 * capture_server.py serves HTTPS with a self-signed cert (the same one the
 * operator already has to click through a browser warning for). This app
 * has no UI path to click through that warning, so it trusts any cert --
 * acceptable specifically because this is a same-LAN-only internal tool
 * with no public exposure, the same effective trust posture the browser
 * flow already has once the operator has clicked "proceed anyway" once.
 * Never reuse this trust-all client for anything that leaves the LAN.
 */
object UploadClient {

    data class CategoryResult(val key: String, val label: String, val prefix: String)

    /** Keeps a catalogue rejection distinct from a transport failure.
     * Unknown labels must stop before capture; an unreachable server should
     * remain retryable and must not falsely brand a real label invalid. */
    data class CategoryResolution(
        val category: CategoryResult?,
        val serverReached: Boolean,
        val error: String?
    )

    data class SaveResult(
        val ok: Boolean,
        val error: String?,
        val duplicate: Boolean,
        val blurry: Boolean,
        val notVisible: Boolean,
        val raw: JSONObject
    )

    private val client: OkHttpClient by lazy {
        val trustAllCerts = arrayOf<TrustManager>(object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
            override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
            override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
        })
        val sslContext = SSLContext.getInstance("TLS")
        sslContext.init(null, trustAllCerts, SecureRandom())
        OkHttpClient.Builder()
            .sslSocketFactory(sslContext.socketFactory, trustAllCerts[0] as X509TrustManager)
            .hostnameVerifier(HostnameVerifier { _, _ -> true })
            // ARADHANA runs capture_server.py on both active adapters. Give
            // OkHttp both routes explicitly so LAN cable/Wi-Fi transitions do
            // not depend on Android's mDNS cache expiring first.
            .dns(object : Dns {
                override fun lookup(hostname: String): List<InetAddress> {
                    if (!hostname.equals("ARADHANA.local", ignoreCase = true)) {
                        return Dns.SYSTEM.lookup(hostname)
                    }
                    return listOf("192.168.0.3", "192.168.0.7")
                        .map(InetAddress::getByName)
                }
            })
            // Three full-resolution Sony JPEGs can exceed 40 MB, followed
            // by synchronous local SAM segmentation and full-detail
            // compositing. OkHttp's 10-second defaults would report a false
            // upload failure while the laptop was correctly still working.
            .connectTimeout(15, TimeUnit.SECONDS)
            .writeTimeout(3, TimeUnit.MINUTES)
            .readTimeout(5, TimeUnit.MINUTES)
            .callTimeout(8, TimeUnit.MINUTES)
            .build()
    }

    /** capture_server.py's /api/capture/resolve_category. Category resolution
     * is a hard pre-capture gate: otherwise a bad/misread code consumes three
     * full-resolution shutters and fails only at the final save. */
    suspend fun resolveCategory(baseUrl: String, tagCode: String): CategoryResolution = withContext(Dispatchers.IO) {
        try {
            val encoded = java.net.URLEncoder.encode(tagCode, "UTF-8")
            val request = Request.Builder()
                .url("${baseUrl.trimEnd('/')}/api/capture/resolve_category?tag_code=$encoded")
                .get()
                .build()
            client.newCall(request).execute().use { response ->
                val text = response.body?.string() ?: "{}"
                val json = try { JSONObject(text) } catch (_: Exception) { JSONObject() }
                if (!json.optBoolean("ok", false)) {
                    return@withContext CategoryResolution(
                        category = null,
                        serverReached = true,
                        error = json.optString("error").ifBlank { "Unknown category" }
                    )
                }
                CategoryResolution(
                    category = CategoryResult(
                        key = json.getString("key"),
                        label = json.getString("label"),
                        prefix = json.getString("prefix")
                    ),
                    serverReached = true,
                    error = null
                )
            }
        } catch (e: Exception) {
            CategoryResolution(category = null, serverReached = false, error = e.message)
        }
    }

    /** Per-tag stud/rhodium-accent flag, persisted server-side (see
     * capture_server.py's /api/capture/stud_flag) -- 2026-08-19, explicit
     * request: a correction made once for a tag must survive a delete+
     * recapture of that same item, so this is looked up fresh whenever a
     * tag resolves, not cached across items. Null on any failure -- the
     * live UI falls back to the on-device auto-guess when this can't be
     * reached. This flag remains advisory; category resolution does not. */
    suspend fun getStudFlag(baseUrl: String, tagCode: String): Boolean? = withContext(Dispatchers.IO) {
        try {
            val encoded = java.net.URLEncoder.encode(tagCode, "UTF-8")
            val request = Request.Builder()
                .url("${baseUrl.trimEnd('/')}/api/capture/stud_flag?tag_code=$encoded")
                .get()
                .build()
            client.newCall(request).execute().use { response ->
                val text = response.body?.string() ?: "{}"
                val json = try { JSONObject(text) } catch (_: Exception) { JSONObject() }
                if (!json.optBoolean("ok", false)) return@withContext null
                json.getBoolean("has_stud")
            }
        } catch (e: Exception) {
            null
        }
    }

    /** Staff correction from the live preview overlay. Returns the saved
     * value on success (should echo hasStud), null on failure -- caller
     * should NOT optimistically update its own UI state past what this
     * confirms actually persisted. */
    suspend fun setStudFlag(baseUrl: String, tagCode: String, hasStud: Boolean, staffName: String): Boolean? =
        withContext(Dispatchers.IO) {
            try {
                val body = JSONObject().apply {
                    put("tag_code", tagCode)
                    put("has_stud", hasStud)
                    put("staff_name", staffName)
                }.toString().toRequestBody("application/json".toMediaType())
                val request = Request.Builder()
                    .url("${baseUrl.trimEnd('/')}/api/capture/stud_flag")
                    .post(body)
                    .build()
                client.newCall(request).execute().use { response ->
                    val text = response.body?.string() ?: "{}"
                    val json = try { JSONObject(text) } catch (_: Exception) { JSONObject() }
                    if (!json.optBoolean("ok", false)) return@withContext null
                    json.getBoolean("has_stud")
                }
            } catch (e: Exception) {
                null
            }
        }

    suspend fun savePair(
        baseUrl: String,
        tagCode: String,
        staffName: String,
        jewelJpeg: ByteArray,
        tagJpeg: ByteArray,
        overrideDuplicate: Boolean = false,
        overrideBlur: Boolean = false,
        overrideVisibility: Boolean = false
    ): SaveResult = withContext(Dispatchers.IO) {
        val bodyBuilder = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("tag_code", tagCode)
            .addFormDataPart("staff_name", staffName)
            .addFormDataPart("jewel", "jewel.jpg", jewelJpeg.toRequestBody("image/jpeg".toMediaType()))
            .addFormDataPart("tag", "tag.jpg", tagJpeg.toRequestBody("image/jpeg".toMediaType()))
        if (overrideDuplicate) bodyBuilder.addFormDataPart("override_duplicate", "1")
        if (overrideBlur) bodyBuilder.addFormDataPart("override_blur", "1")
        if (overrideVisibility) bodyBuilder.addFormDataPart("override_visibility", "1")

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/capture/save")
            .post(bodyBuilder.build())
            .build()

        client.newCall(request).execute().use { response ->
            val text = response.body?.string() ?: "{}"
            val json = try { JSONObject(text) } catch (_: Exception) { JSONObject() }
            val errorField = if (json.has("error")) json.getString("error") else null
            SaveResult(
                ok = json.optBoolean("ok", false),
                error = errorField,
                duplicate = errorField == "duplicate",
                blurry = errorField == "blurry",
                notVisible = errorField == "not_clearly_visible",
                raw = json
            )
        }
    }

    /** RSC 2 3-angle workflow -- posts MAIN/ANGLE_1/ANGLE_2 to the laptop.
     * capture_tool.save_multi preserves the sources in a hidden recovery
     * archive and atomically publishes one 60/20/20 composite as <tag>.jpg.
     * Only the decoded tag_code crosses the wire; no tag photo is archived. */
    suspend fun saveMulti(
        baseUrl: String,
        tagCode: String,
        staffName: String,
        mainJpeg: ByteArray,
        angle1Jpeg: ByteArray,
        angle2Jpeg: ByteArray,
        overrideDuplicate: Boolean = false,
        overrideBlur: Boolean = false,
        overrideVisibility: Boolean = false
    ): SaveResult = withContext(Dispatchers.IO) {
        val bodyBuilder = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("tag_code", tagCode)
            .addFormDataPart("staff_name", staffName)
            .addFormDataPart("main", "main.jpg", mainJpeg.toRequestBody("image/jpeg".toMediaType()))
            .addFormDataPart("angle1", "angle1.jpg", angle1Jpeg.toRequestBody("image/jpeg".toMediaType()))
            .addFormDataPart("angle2", "angle2.jpg", angle2Jpeg.toRequestBody("image/jpeg".toMediaType()))
        if (overrideDuplicate) bodyBuilder.addFormDataPart("override_duplicate", "1")
        if (overrideBlur) bodyBuilder.addFormDataPart("override_blur", "1")
        if (overrideVisibility) bodyBuilder.addFormDataPart("override_visibility", "1")

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/capture/save_multi")
            .post(bodyBuilder.build())
            .build()

        client.newCall(request).execute().use { response ->
            val text = response.body?.string() ?: "{}"
            val json = try { JSONObject(text) } catch (_: Exception) { JSONObject() }
            val errorField = if (json.has("error")) json.getString("error") else null
            SaveResult(
                ok = json.optBoolean("ok", false),
                error = errorField,
                duplicate = errorField == "duplicate",
                blurry = errorField == "blurry",
                notVisible = errorField == "not_clearly_visible",
                raw = json
            )
        }
    }

    /** File-backed variant used by the durable background queue. It streams
     * originals from app-private storage instead of materialising another
     * 40-60 MB set of ByteArrays while the next item is being captured. */
    suspend fun saveMultiFiles(
        baseUrl: String,
        tagCode: String,
        staffName: String,
        mainJpeg: File,
        angle1Jpeg: File,
        angle2Jpeg: File
    ): SaveResult = withContext(Dispatchers.IO) {
        val jpeg = "image/jpeg".toMediaType()
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("tag_code", tagCode)
            .addFormDataPart("staff_name", staffName)
            .addFormDataPart("main", "main.jpg", mainJpeg.asRequestBody(jpeg))
            .addFormDataPart("angle1", "angle1.jpg", angle1Jpeg.asRequestBody(jpeg))
            .addFormDataPart("angle2", "angle2.jpg", angle2Jpeg.asRequestBody(jpeg))
            .build()
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/capture/save_multi")
            .post(body)
            .build()
        client.newCall(request).execute().use { response ->
            parseSaveResult(response.body?.string() ?: "{}")
        }
    }

    /** File-backed two-image variant; see [saveMultiFiles]. */
    suspend fun savePairFiles(
        baseUrl: String,
        tagCode: String,
        staffName: String,
        jewelJpeg: File,
        tagJpeg: File
    ): SaveResult = withContext(Dispatchers.IO) {
        val jpeg = "image/jpeg".toMediaType()
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("tag_code", tagCode)
            .addFormDataPart("staff_name", staffName)
            .addFormDataPart("jewel", "jewel.jpg", jewelJpeg.asRequestBody(jpeg))
            .addFormDataPart("tag", "tag.jpg", tagJpeg.asRequestBody(jpeg))
            .build()
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/capture/save")
            .post(body)
            .build()
        client.newCall(request).execute().use { response ->
            parseSaveResult(response.body?.string() ?: "{}")
        }
    }

    private fun parseSaveResult(text: String): SaveResult {
        val json = try { JSONObject(text) } catch (_: Exception) { JSONObject() }
        val errorField = if (json.has("error")) json.optString("error").ifBlank { null } else null
        return SaveResult(
            ok = json.optBoolean("ok", false),
            error = errorField,
            duplicate = errorField == "duplicate",
            blurry = errorField == "blurry",
            notVisible = errorField == "not_clearly_visible",
            raw = json
        )
    }
}
