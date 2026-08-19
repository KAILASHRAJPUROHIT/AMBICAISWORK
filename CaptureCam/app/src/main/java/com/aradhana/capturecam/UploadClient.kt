package com.aradhana.capturecam

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.security.SecureRandom
import java.security.cert.X509Certificate
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

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
            .build()
    }

    /** capture_server.py's /api/capture/resolve_category -- the tag's code
     * prefix is the sole source of truth for its category, this just gives
     * the phone app the same resolution the browser capture tool already
     * had. Added 2026-08-19 for category-aware behavior on-device (the
     * ghungroo/dangler symmetry check needs to know which items actually
     * have a mirror-symmetric pair/halves worth comparing). Null on any
     * failure -- callers must treat this as advisory-only and never block
     * a capture on it being unavailable. */
    suspend fun resolveCategory(baseUrl: String, tagCode: String): CategoryResult? = withContext(Dispatchers.IO) {
        try {
            val encoded = java.net.URLEncoder.encode(tagCode, "UTF-8")
            val request = Request.Builder()
                .url("${baseUrl.trimEnd('/')}/api/capture/resolve_category?tag_code=$encoded")
                .get()
                .build()
            client.newCall(request).execute().use { response ->
                val text = response.body?.string() ?: "{}"
                val json = try { JSONObject(text) } catch (_: Exception) { JSONObject() }
                if (!json.optBoolean("ok", false)) return@withContext null
                CategoryResult(
                    key = json.getString("key"),
                    label = json.getString("label"),
                    prefix = json.getString("prefix")
                )
            }
        } catch (e: Exception) {
            null
        }
    }

    /** Per-tag stud/rhodium-accent flag, persisted server-side (see
     * capture_server.py's /api/capture/stud_flag) -- 2026-08-19, explicit
     * request: a correction made once for a tag must survive a delete+
     * recapture of that same item, so this is looked up fresh whenever a
     * tag resolves, not cached across items. Null on any failure -- the
     * live UI falls back to the on-device auto-guess when this can't be
     * reached, same "advisory, never blocking" posture as resolveCategory. */
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

    /** RSC 2 3-angle workflow -- posts to capture_server.py's
     * /api/capture/save_multi (capture_tool.save_multi): MAIN/ANGLE_1/
     * ANGLE_2 -> <tag>.jpg/<tag>_1.jpg/<tag>_2.jpg. No separate tag image
     * upload -- same as save_pair, only the already-decoded tag_code
     * crosses the wire. */
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
}
