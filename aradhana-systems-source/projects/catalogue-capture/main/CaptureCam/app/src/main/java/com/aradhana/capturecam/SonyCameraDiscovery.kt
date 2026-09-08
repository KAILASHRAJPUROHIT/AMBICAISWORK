package com.aradhana.capturecam

import android.content.Context
import android.net.ConnectivityManager
import android.net.LinkAddress
import android.util.Log
import com.jcraft.jsch.JSch
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * LAN rediscovery for the Sony camera's SSH endpoint (2026-08-28).
 *
 * Both the tablet and the camera get their address from the shop's DHCP
 * server, and confirmed live: neither address is stable across a Wi-Fi
 * reconnect -- the tablet moved 192.168.0.22 -> 192.168.0.18 and the camera
 * moved 192.168.0.14 -> 192.168.0.20 in the same session, with no warning
 * beyond "connection refused" (something else now holds the old IP) or a
 * timeout (nothing there at all). A hardcoded/remembered IP is therefore
 * never durable. This sweeps the tablet's OWN current /24 for a host that
 * both has port 22 open AND authenticates with the camera's own SSH
 * credentials -- nothing else on a normal shop LAN is expected to do both,
 * so a match is trustworthy without needing any camera-specific banner.
 *
 * The proper complementary fix is a DHCP reservation on the router (MAC ->
 * fixed IP for both devices) so this rarely has to run at all -- that's a
 * network-admin change outside this app's reach, this is the software
 * fallback for when it hasn't been done (or the router itself changes).
 */
object SonyCameraDiscovery {
    private const val TAG = "SonyCameraDiscovery"
    private const val SSH_PORT = 22
    private const val PORT_PROBE_TIMEOUT_MS = 350
    private const val SSH_AUTH_TIMEOUT_MS = 2_500
    private const val MAX_HOSTS_SCANNED = 254
    private const val SCAN_PARALLELISM = 32

    /** Every other host in the tablet's own current IPv4 /24 (or narrower,
     * if the real prefix is more specific) -- capped at [MAX_HOSTS_SCANNED]
     * so a misconfigured huge subnet can't turn this into a multi-minute
     * scan. Returns empty if the tablet has no usable IPv4 link right now. */
    private fun subnetCandidates(context: Context): List<String> {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
            ?: return emptyList()
        val network = cm.activeNetwork ?: return emptyList()
        val linkProperties = cm.getLinkProperties(network) ?: return emptyList()
        val link: LinkAddress = linkProperties.linkAddresses.firstOrNull {
            it.address is java.net.Inet4Address && !it.address.isLoopbackAddress
        } ?: return emptyList()
        val selfBytes = link.address.address
        val prefix = link.prefixLength.coerceIn(24, 30) // never sweep more than a /24 worth
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

    private fun hasOpenSshPort(ip: String): Boolean = try {
        Socket().use { socket ->
            socket.connect(InetSocketAddress(InetAddress.getByName(ip), SSH_PORT), PORT_PROBE_TIMEOUT_MS)
            true
        }
    } catch (_: Exception) {
        false
    }

    private fun authenticatesAsCamera(ip: String, user: String, password: String): Boolean {
        val jsch = JSch()
        return try {
            val session = jsch.getSession(user, ip, SSH_PORT)
            session.setPassword(password)
            session.setConfig("StrictHostKeyChecking", "no")
            session.timeout = SSH_AUTH_TIMEOUT_MS
            session.connect(SSH_AUTH_TIMEOUT_MS)
            session.disconnect()
            true
        } catch (e: Exception) {
            Log.d(TAG, "Candidate $ip did not authenticate as the camera: ${e.message}")
            false
        }
    }

    /** Sweeps the current subnet for a host that opens port 22 AND accepts
     * the camera's own SSH credentials. Blocking -- call off the main
     * thread. [preferredIp] (the last-known/saved address) is checked
     * first, standalone, before paying for a full subnet sweep, since the
     * common case is that nothing has changed. Returns null if no match
     * was found anywhere on the subnet. */
    fun discoverCameraIp(context: Context, user: String, password: String, preferredIp: String?): String? {
        if (!preferredIp.isNullOrBlank() && hasOpenSshPort(preferredIp) &&
            authenticatesAsCamera(preferredIp, user, password)
        ) {
            return preferredIp
        }
        val candidates = subnetCandidates(context).filter { it != preferredIp }
        if (candidates.isEmpty()) {
            Log.w(TAG, "No subnet candidates to scan -- tablet has no usable IPv4 link")
            return null
        }
        Log.i(TAG, "Sony camera IP rediscovery: sweeping ${candidates.size} hosts for an open SSH port")
        val pool = Executors.newFixedThreadPool(SCAN_PARALLELISM)
        val openHosts = try {
            candidates
                .map { ip -> pool.submit<String?> { if (hasOpenSshPort(ip)) ip else null } }
                .mapNotNull { it.get(PORT_PROBE_TIMEOUT_MS + 500L, TimeUnit.MILLISECONDS) }
        } finally {
            pool.shutdown()
        }
        Log.i(TAG, "Sony camera IP rediscovery: ${openHosts.size} host(s) with SSH open: $openHosts")
        val match = openHosts.firstOrNull { authenticatesAsCamera(it, user, password) }
        if (match != null) {
            Log.i(TAG, "Sony camera IP rediscovery: found camera at $match")
        } else {
            Log.w(TAG, "Sony camera IP rediscovery: no host on the subnet accepted the camera's credentials")
        }
        return match
    }
}
