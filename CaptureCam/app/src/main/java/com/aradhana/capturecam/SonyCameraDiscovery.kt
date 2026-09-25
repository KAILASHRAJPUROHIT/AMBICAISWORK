package com.aradhana.capturecam

import android.content.Context
import android.net.ConnectivityManager
import android.net.LinkAddress
import android.util.Log
import com.jcraft.jsch.JSch
import java.net.Inet4Address
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.NetworkInterface
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

    // ------------------------------------------------------------------
    // Hotspot preflight (2026-09-25)
    //
    // The camera now joins the TABLET'S OWN hotspot instead of the shop
    // Wi-Fi (shop Wi-Fi showed 25-86% packet loss to the camera; hotspot
    // measured 0% loss and a steady 25fps live view). The tablet stays on
    // the shop Wi-Fi at the same time (AP+STA). Everything below only ever
    // looks at the tablet's hotspot subnet, where the camera is the only
    // possible client -- so unlike the shop-LAN sweep (disabled in
    // SonyProductionCamera) it cannot land on some other device that
    // happens to accept the same login.
    // ------------------------------------------------------------------

    enum class PreflightState { OK, REDISCOVERED, HOTSPOT_OFF, CAMERA_NOT_FOUND }

    data class PreflightResult(
        val state: PreflightState,
        val cameraIp: String?,
        val rttMs: Long?,
        val message: String
    )

    private val TETHER_IFACE_PREFIXES = listOf("wlan", "ap", "swlan", "softap")

    /** IPv4 addresses the tablet itself owns on its hotspot (AP) interface:
     * private-range addresses on a Wi-Fi/AP-style interface that is NOT the
     * active client network. Mobile-data interfaces are excluded by name so
     * a carrier 10.x address is never mistaken for the hotspot. */
    fun hotspotSubnets(context: Context): List<Pair<Inet4Address, Int>> {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
        val activeAddrs = cm?.activeNetwork?.let { cm.getLinkProperties(it) }
            ?.linkAddresses?.mapNotNull { it.address.hostAddress }?.toSet() ?: emptySet()
        val out = ArrayList<Pair<Inet4Address, Int>>()
        try {
            for (ni in NetworkInterface.getNetworkInterfaces()) {
                if (!ni.isUp || ni.isLoopback) continue
                val name = ni.name.lowercase()
                if (TETHER_IFACE_PREFIXES.none { name.startsWith(it) }) continue
                for (ia in ni.interfaceAddresses) {
                    val a = ia.address as? Inet4Address ?: continue
                    if (a.isLoopbackAddress || !a.isSiteLocalAddress) continue
                    if (a.hostAddress in activeAddrs) continue
                    out += a to ia.networkPrefixLength.toInt()
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "hotspotSubnets failed: ${e.message}")
        }
        return out
    }

    private fun ipToInt(b: ByteArray): Int =
        ((b[0].toInt() and 0xFF) shl 24) or ((b[1].toInt() and 0xFF) shl 16) or
            ((b[2].toInt() and 0xFF) shl 8) or (b[3].toInt() and 0xFF)

    private fun isInSubnet(ip: String, self: Inet4Address, prefix: Int): Boolean = try {
        val a = InetAddress.getByName(ip).address
        val mask = 0xFFFFFFFF.toInt() shl (32 - prefix.coerceIn(8, 30))
        a.size == 4 && (ipToInt(a) and mask) == (ipToInt(self.address) and mask)
    } catch (_: Exception) {
        false
    }

    private fun probeRttMs(ip: String, attempts: Int = 2): Long? {
        repeat(attempts) {
            val t0 = System.nanoTime()
            try {
                Socket().use { it.connect(InetSocketAddress(InetAddress.getByName(ip), SSH_PORT), 1_500) }
                return (System.nanoTime() - t0) / 1_000_000L
            } catch (_: Exception) {
            }
        }
        return null
    }

    private fun hostsOnSubnet(self: Inet4Address, prefix: Int): List<String> {
        val hostBits = 32 - prefix.coerceIn(24, 30)
        val count = (1 shl hostBits).coerceAtMost(MAX_HOSTS_SCANNED + 2)
        val selfInt = ipToInt(self.address)
        val net = selfInt and (0xFFFFFFFF.toInt() shl hostBits)
        val list = ArrayList<String>(count)
        for (h in 1 until count - 1) {
            val ip = net or h
            if (ip == selfInt) continue
            list += "${ip ushr 24 and 0xFF}.${ip ushr 16 and 0xFF}.${ip ushr 8 and 0xFF}.${ip and 0xFF}"
        }
        return list
    }

    /** Blocking; call off the main thread. Safe: plain TCP probes, plus an
     * SSH credential check ONLY against hosts on the hotspot subnet. */
    fun hotspotPreflight(context: Context, configuredIp: String, user: String, password: String): PreflightResult {
        val subnets = hotspotSubnets(context)
        if (subnets.isEmpty()) {
            return PreflightResult(
                PreflightState.HOTSPOT_OFF, null, null,
                "Tablet hotspot is OFF - turn it on and connect the camera to it"
            )
        }
        if (subnets.any { (self, prefix) -> isInSubnet(configuredIp, self, prefix) }) {
            probeRttMs(configuredIp)?.let {
                return PreflightResult(
                    PreflightState.OK, configuredIp, it,
                    "Hotspot OK - camera $configuredIp reachable (${it}ms)"
                )
            }
        }
        for ((self, prefix) in subnets) {
            val pool = Executors.newFixedThreadPool(SCAN_PARALLELISM)
            val open = try {
                hostsOnSubnet(self, prefix)
                    .map { ip -> pool.submit<String?> { if (hasOpenSshPort(ip)) ip else null } }
                    .mapNotNull { runCatching { it.get(PORT_PROBE_TIMEOUT_MS + 500L, TimeUnit.MILLISECONDS) }.getOrNull() }
            } finally {
                pool.shutdown()
            }
            val match = open.firstOrNull { authenticatesAsCamera(it, user, password) }
            if (match != null) {
                return PreflightResult(
                    PreflightState.REDISCOVERED, match, probeRttMs(match),
                    "Camera found on hotspot at $match (was $configuredIp)"
                )
            }
        }
        return PreflightResult(
            PreflightState.CAMERA_NOT_FOUND, null, null,
            "Camera NOT on tablet hotspot - connect the camera's Wi-Fi to the tablet hotspot"
        )
    }
}
