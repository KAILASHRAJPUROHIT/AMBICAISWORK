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
