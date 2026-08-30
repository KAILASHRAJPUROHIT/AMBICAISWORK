package com.aradhana.capturecam

import android.content.Context
import android.net.ConnectivityManager
import android.net.LinkAddress
import android.net.NetworkCapabilities
import android.util.Log
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Socket
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocket
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager
import org.json.JSONObject

/**
 * LAN rediscovery for capture_server.py's own address (2026-08-28), the
 * same "everything on this LAN drifts" problem SonyCameraDiscovery already
 * solves for the camera -- confirmed live the same day: the laptop hosting
 * capture_server.py had moved off both addresses UploadClient's DNS
 * override hardcoded (192.168.0.3 / .7), to .12, with zero visible failure
 * beyond an operator stuck on "Checking tag category..." for as long as the
 * call's timeout allowed. mDNS resolution is tried first and should be
 * enough on its own when the LAN actually relays multicast -- this sweep is
 * the hardwall for when it doesn't, so a laptop IP change never again
 * silently blocks every capture.
 */
object ServerDiscovery {
    private const val TAG = "ServerDiscovery"
    private const val PORT_PROBE_TIMEOUT_MS = 350
    private const val HTTP_PROBE_TIMEOUT_MS = 2_000
    private const val MAX_HOSTS_SCANNED = 254
    private const val SCAN_PARALLELISM = 32

    private val trustAllSocketFactory by lazy {
        val trustAllCerts = arrayOf<TrustManager>(object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
            override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
            override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
        })
        val sslContext = SSLContext.getInstance("TLS")
        sslContext.init(null, trustAllCerts, SecureRandom())
        sslContext.socketFactory
    }

    private fun subnetCandidates(context: Context): List<String> {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
            ?: return emptyList()
        val network = cm.activeNetwork ?: return emptyList()
        val linkProperties = cm.getLinkProperties(network) ?: return emptyList()
        val link: LinkAddress = linkProperties.linkAddresses.firstOrNull {
            it.address is java.net.Inet4Address && !it.address.isLoopbackAddress
        } ?: return emptyList()
        val selfBytes = link.address.address
        val prefix = link.prefixLength.coerceIn(24, 30)
        val hostBits = 32 - prefix
        val hostCount = (1 shl hostBits).coerceAtMost(MAX_HOSTS_SCANNED + 2)
        val base = ByteArray(4)
        val mask = (0xFFFFFFFF.toInt() shl hostBits)
        val selfInt = ((selfBytes[0].toInt() and 0xFF) shl 24) or
            ((selfBytes[1].toInt() and 0xFF) shl 16) or
            ((selfBytes[2].toInt() and 0xFF) shl 8) or
            (selfBytes[3].toInt() and 0xFF)
        val networkInt = selfInt and mask
        val selfAddress = link.address.hostAddress
        val candidates = ArrayList<String>(hostCount)
        for (host in 1 until hostCount - 1) {
            val ipInt = networkInt or host
            base[0] = (ipInt ushr 24 and 0xFF).toByte()
            base[1] = (ipInt ushr 16 and 0xFF).toByte()
            base[2] = (ipInt ushr 8 and 0xFF).toByte()
            base[3] = (ipInt and 0xFF).toByte()
            val ip = "${base[0].toInt() and 0xFF}.${base[1].toInt() and 0xFF}." +
                "${base[2].toInt() and 0xFF}.${base[3].toInt() and 0xFF}"
            if (ip != selfAddress) candidates += ip
            if (candidates.size >= MAX_HOSTS_SCANNED) break
        }
        return candidates
    }

    private fun hasOpenPort(ip: String, port: Int): Boolean = try {
        Socket().use { socket ->
            socket.connect(InetSocketAddress(InetAddress.getByName(ip), port), PORT_PROBE_TIMEOUT_MS)
            true
        }
    } catch (_: Exception) {
        false
    }

    /** True only for capture_server.py itself -- /api/heartbeat's JSON
     * always carries "capture_version", a key nothing else on a normal
     * shop LAN is expected to return, so a match is trustworthy without
     * needing a fixed IP or a certificate to check. */
    private fun lanSocketFactory(context: Context): javax.net.SocketFactory? {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return null
        // NET_CAPABILITY_INTERNET only means "intended to provide internet"
        // and is set on ANY Wi-Fi network -- including the Sony camera AP the
        // PTP route binds to, which is exactly the network this must avoid.
        // NET_CAPABILITY_VALIDATED is only granted after Android confirms
        // real connectivity, so it actually distinguishes the shop LAN.
        return cm.allNetworks.firstOrNull { network ->
            cm.getNetworkCapabilities(network)?.let { caps ->
                caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) &&
                    caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
                    caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
            } == true
        }?.socketFactory
    }

    private fun isCaptureServer(context: Context, ip: String, port: Int): Boolean = try {
        // HttpsURLConnection sometimes re-enters the platform trust policy
        // during its lazy output-stream handshake on Android 16, despite its
        // per-connection trust-all factory. Use one explicit TLS socket for
        // the tiny LAN-only identity probe, with the same trust factory.
        val raw = (lanSocketFactory(context) ?: javax.net.SocketFactory.getDefault()).createSocket()
        raw.connect(InetSocketAddress(ip, port), HTTP_PROBE_TIMEOUT_MS)
        (trustAllSocketFactory.createSocket(raw, ip, port, true) as SSLSocket).use { socket ->
            socket.soTimeout = HTTP_PROBE_TIMEOUT_MS
            socket.startHandshake()
            val out = socket.outputStream.bufferedWriter(Charsets.US_ASCII)
            out.write("POST /api/heartbeat HTTP/1.1\r\nHost: $ip:$port\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            out.flush()
            val response = socket.inputStream.bufferedReader(Charsets.UTF_8).readText()
            response.startsWith("HTTP/1.1 200") && response.contains("\"capture_version\"")
        }
    } catch (e: Exception) {
        Log.w(TAG, "capture_server.py identity probe failed for $ip:$port: ${e.message}")
        false
    }

    private inline fun HttpsURLConnection.use(block: (HttpsURLConnection) -> Boolean): Boolean =
        try {
            block(this)
        } finally {
            disconnect()
        }

    /** Sweeps the tablet's current subnet for capture_server.py's HTTPS
     * port. Blocking -- call off the main thread. [preferredIp] (the
     * last-known/saved address) is checked first, standalone, since the
     * common case is that nothing has changed. Returns null if no match
     * was found anywhere on the subnet. */
    fun discoverServerIp(context: Context, port: Int, preferredIp: String?): String? {
        if (!preferredIp.isNullOrBlank() && hasOpenPort(preferredIp, port) &&
            isCaptureServer(context, preferredIp, port)
        ) {
            return preferredIp
        }
        val candidates = subnetCandidates(context).filter { it != preferredIp }
        if (candidates.isEmpty()) {
            Log.w(TAG, "No subnet candidates to scan -- tablet has no usable IPv4 link")
            return null
        }
        Log.i(TAG, "capture_server.py IP rediscovery: sweeping ${candidates.size} hosts for port $port")
        val pool = Executors.newFixedThreadPool(SCAN_PARALLELISM)
        val openHosts = try {
            candidates
                .map { ip -> pool.submit<String?> { if (hasOpenPort(ip, port)) ip else null } }
                .mapNotNull { it.get(PORT_PROBE_TIMEOUT_MS + 500L, TimeUnit.MILLISECONDS) }
        } finally {
            pool.shutdown()
        }
        Log.i(TAG, "capture_server.py IP rediscovery: ${openHosts.size} host(s) with port $port open: $openHosts")
        val match = openHosts.firstOrNull { isCaptureServer(context, it, port) }
        if (match != null) {
            Log.i(TAG, "capture_server.py IP rediscovery: found server at $match")
        } else {
            Log.w(TAG, "capture_server.py IP rediscovery: no host on the subnet answered as capture_server.py")
        }
        return match
    }
}
