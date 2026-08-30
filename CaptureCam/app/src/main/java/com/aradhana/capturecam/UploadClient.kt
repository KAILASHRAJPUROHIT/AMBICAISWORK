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
import javax.net.SocketFactory
import android.net.ConnectivityManager
import android.net.NetworkCapabilities

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

    // Set by MainActivity after a background ServerDiscovery sweep finds
    // capture_server.py's current real address (2026-08-28 hardwall for the
    // laptop's own IP drifting, same as the camera/tablet drift already
    // fixed today) -- consulted BEFORE mDNS and the static fallback in the
    // Dns override below, since it's the most recently live-verified route.
    @Volatile var discoveredServerIp: String? = null
    @Volatile private var lanSocketFactory: SocketFactory? = null

    /**
     * Indirection so the shared OkHttpClient below can stay a singleton while
     * still honouring a route that changes at runtime. Rebuilding the client
     * per request (an earlier attempt at this) gave every call its own
     * connection pool and dispatcher threads and re-ran the TLS setup each
     * time -- on a path that uploads 12-17MB originals, that meant no
     * keep-alive and constant thread churn. Resolving the current factory
     * per socket costs nothing and keeps the pool intact.
     */
    private object RouteAwareSocketFactory : SocketFactory() {
        private fun delegate(): SocketFactory = lanSocketFactory ?: SocketFactory.getDefault()
        override fun createSocket(): java.net.Socket = delegate().createSocket()
        override fun createSocket(host: String?, port: Int): java.net.Socket =
            delegate().createSocket(host, port)
        override fun createSocket(
            host: String?, port: Int, localHost: java.net.InetAddress?, localPort: Int
        ): java.net.Socket = delegate().createSocket(host, port, localHost, localPort)
        override fun createSocket(host: java.net.InetAddress?, port: Int): java.net.Socket =
            delegate().createSocket(host, port)
        override fun createSocket(
            address: java.net.InetAddress?, port: Int,
            localAddress: java.net.InetAddress?, localPort: Int
        ): java.net.Socket = delegate().createSocket(address, port, localAddress, localPort)
    }

    /** Keep catalogue traffic on the ordinary Wi-Fi with Internet, even when
     * SonyWifiConnectionManager binds the PTP process route to the camera AP. */
    fun refreshLanRoute(context: android.content.Context) {
        val cm = context.getSystemService(android.content.Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
            ?: return
        // NET_CAPABILITY_INTERNET only means "intended to provide internet"
        // and is set on ANY Wi-Fi network -- including the Sony camera AP the
        // PTP route binds to, which is exactly the network this must avoid.
        // NET_CAPABILITY_VALIDATED is only granted after Android confirms
        // real connectivity, so it actually distinguishes the shop LAN.
        val route = cm.allNetworks.firstOrNull { network ->
            cm.getNetworkCapabilities(network)?.let { caps ->
                caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) &&
                    caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
                    caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
            } == true
        } ?: return
        lanSocketFactory = route.socketFactory
    }

    /**
     * Resolve the capture service immediately before a queued job uploads.
     * WorkManager may run hours after a job was staged, after DHCP has changed
     * both tablet and laptop addresses. A manifest address is only a hint;
     * verify it first, then sweep the tablet's current subnet when needed.
     */
    suspend fun resolveDeliveryBaseUrl(context: android.content.Context, baseUrl: String): String =
        withContext(Dispatchers.IO) {
            val uri = try { java.net.URI(baseUrl) } catch (_: Exception) { return@withContext baseUrl }
            val port = uri.port.takeIf { it > 0 } ?: 7660
            val preferred = discoveredServerIp
                ?: context.getSharedPreferences("capturecam", android.content.Context.MODE_PRIVATE)
                    .getString("capture_server_ip", null)
                ?: uri.host
            val found = ServerDiscovery.discoverServerIp(context.applicationContext, port, preferred)
                ?: return@withContext baseUrl
            discoveredServerIp = found
            context.getSharedPreferences("capturecam", android.content.Context.MODE_PRIVATE)
                .edit().putString("capture_server_ip", found).apply()
            "${uri.scheme ?: "https"}://$found:$port"
        }

    data class CategoryResult(val key: String, val label: String, val prefix: String)

    /** Keeps a catalogue rejection distinct from a transport failure.
     * Unknown labels must stop before capture; an unreachable server should
     * remain retryable and must not falsely brand a real label invalid. */
    data class CategoryResolution(
        val category: CategoryResult?,
        val serverReached: Boolean,
        val error: String?
    )

    /** Exact pre-capture duplicate check. This uses the same server-side
     * dedup registry that ultimately saves the item, so the tablet never
     * wastes a Sony capture cycle on a tag already delivered. */
    data class DuplicateResolution(
        val duplicate: Boolean,
        val prior: JSONObject?,
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
            .socketFactory(RouteAwareSocketFactory)
            .sslSocketFactory(sslContext.socketFactory, trustAllCerts[0] as X509TrustManager)
            .hostnameVerifier(HostnameVerifier { _, _ -> true })
            // ARADHANA runs capture_server.py on both active adapters. Real
            // mDNS resolution (Dns.SYSTEM, which Android resolves via its
            // built-in .local support) is tried FIRST so this always
            // reaches the laptop's actual current address -- this same LAN
            // has now shown DHCP-drift on every device checked (tablet,
            // camera, and the laptop itself: it moved off 192.168.0.7 to
            // .12 while these two addresses stayed hardcoded, leaving every
            // category/upload call aimed at dead IPs with no failure
            // visible until this got noticed). discoveredServerIp (a live
            // ServerDiscovery sweep result) is tried before even that; the
            // old hardcoded pair is kept, appended, ONLY as a last-resort
            // fallback for a network that blocks mDNS multicast entirely --
            // never as the primary route.
            .dns(object : Dns {
                override fun lookup(hostname: String): List<InetAddress> {
                    if (!hostname.equals("ARADHANA.local", ignoreCase = true)) {
                        return Dns.SYSTEM.lookup(hostname)
                    }
                    val discovered = discoveredServerIp?.let { ip ->
                        try { listOf(InetAddress.getByName(ip)) } catch (_: Exception) { emptyList() }
                    } ?: emptyList()
                    val resolved = try {
                        Dns.SYSTEM.lookup(hostname)
                    } catch (_: Exception) {
                        emptyList()
                    }
                    val fallback = listOf("192.168.0.12", "192.168.0.3", "192.168.0.7")
                        .mapNotNull { ip -> try { InetAddress.getByName(ip) } catch (_: Exception) { null } }
                    return (discovered + resolved + fallback).distinct()
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

    // Category/stud-flag lookups are small, fast GETs gating a capture
    // in progress -- reusing `client`'s multi-minute upload timeouts left
    // the operator stuck on "Checking tag category..." for up to 8 minutes
    // whenever the server was slow/unresponsive rather than outright down,
    // since the existing unreachable-server retry UI only fires once the
    // call actually completes/fails. Same TLS/DNS setup as `client`, just
    // with timeouts sized for a metadata call.
    private val metadataClient: OkHttpClient by lazy {
        client.newBuilder()
            .connectTimeout(6, TimeUnit.SECONDS)
            .writeTimeout(6, TimeUnit.SECONDS)
            .readTimeout(6, TimeUnit.SECONDS)
            .callTimeout(8, TimeUnit.SECONDS)
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
            metadataClient.newCall(request).execute().use { response ->
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

    suspend fun checkDuplicate(baseUrl: String, tagCode: String): DuplicateResolution = withContext(Dispatchers.IO) {
        try {
            val encoded = java.net.URLEncoder.encode(tagCode, "UTF-8")
            val request = Request.Builder()
                .url("${baseUrl.trimEnd('/')}/api/capture/check_duplicate?tag_code=$encoded")
                .get()
                .build()
            metadataClient.newCall(request).execute().use { response ->
                val text = response.body?.string() ?: "{}"
                val json = try { JSONObject(text) } catch (_: Exception) { JSONObject() }
                if (!response.isSuccessful) {
                    return@withContext DuplicateResolution(
                        duplicate = false, prior = null, serverReached = false,
                        error = "duplicate check HTTP ${response.code}"
                    )
                }
                DuplicateResolution(
                    duplicate = json.optBoolean("duplicate", false),
                    prior = json.optJSONObject("prior"),
                    serverReached = true,
                    error = null
                )
            }
        } catch (e: Exception) {
            DuplicateResolution(duplicate = false, prior = null, serverReached = false, error = e.message)
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
            metadataClient.newCall(request).execute().use { response ->
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
                metadataClient.newCall(request).execute().use { response ->
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
        angle2Jpeg: File,
        overrideDuplicate: Boolean = false,
        overrideBlur: Boolean = false,
        overrideVisibility: Boolean = false
    ): SaveResult = withContext(Dispatchers.IO) {
        val jpeg = "image/jpeg".toMediaType()
        val bodyBuilder = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("tag_code", tagCode)
            .addFormDataPart("staff_name", staffName)
            .addFormDataPart("main", "main.jpg", mainJpeg.asRequestBody(jpeg))
            .addFormDataPart("angle1", "angle1.jpg", angle1Jpeg.asRequestBody(jpeg))
            .addFormDataPart("angle2", "angle2.jpg", angle2Jpeg.asRequestBody(jpeg))
        if (overrideDuplicate) bodyBuilder.addFormDataPart("override_duplicate", "1")
        if (overrideBlur) bodyBuilder.addFormDataPart("override_blur", "1")
        if (overrideVisibility) bodyBuilder.addFormDataPart("override_visibility", "1")
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/capture/save_multi")
            .post(bodyBuilder.build())
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
        tagJpeg: File,
        overrideDuplicate: Boolean = false,
        overrideBlur: Boolean = false,
        overrideVisibility: Boolean = false
    ): SaveResult = withContext(Dispatchers.IO) {
        val jpeg = "image/jpeg".toMediaType()
        val bodyBuilder = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("tag_code", tagCode)
            .addFormDataPart("staff_name", staffName)
            .addFormDataPart("jewel", "jewel.jpg", jewelJpeg.asRequestBody(jpeg))
            .addFormDataPart("tag", "tag.jpg", tagJpeg.asRequestBody(jpeg))
        if (overrideDuplicate) bodyBuilder.addFormDataPart("override_duplicate", "1")
        if (overrideBlur) bodyBuilder.addFormDataPart("override_blur", "1")
        if (overrideVisibility) bodyBuilder.addFormDataPart("override_visibility", "1")
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/capture/save")
            .post(bodyBuilder.build())
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
