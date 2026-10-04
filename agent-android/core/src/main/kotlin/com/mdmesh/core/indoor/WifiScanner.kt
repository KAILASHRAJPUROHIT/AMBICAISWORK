package com.mdmesh.core.indoor

import android.annotation.SuppressLint
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.wifi.ScanResult
import android.net.wifi.WifiManager
import dagger.hilt.android.qualifiers.ApplicationContext
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Reads nearby Wi-Fi networks as BSSID -> dBm. Android limits apps to a few active scans per two minutes, so a scan
 * request may be refused; in that case the system's own most recent results are used.
 *
 * Phone hotspots and other randomised ("locally administered") addresses move around and are dropped, since they
 * would only teach the survey about things that are not part of the building.
 */
@Singleton
class WifiScanner @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val wifi: WifiManager? = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager

    /** The system's current scan results, no new scan. May be a minute or two old. */
    @SuppressLint("MissingPermission") // location is granted by Device Owner at provisioning
    fun latest(): Map<String, Int> = runCatching { toMap(wifi?.scanResults.orEmpty()) }.getOrDefault(emptyMap())

    /** Request a fresh scan and wait up to [timeoutMs] for it; falls back to the system's latest results. */
    @SuppressLint("MissingPermission", "DEPRECATION")
    fun scan(timeoutMs: Long): Map<String, Int> {
        val w = wifi ?: return emptyMap()
        val latch = CountDownLatch(1)
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(c: Context?, i: Intent?) { latch.countDown() }
        }
        return try {
            context.registerReceiver(receiver, IntentFilter(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION))
            val started = runCatching { w.startScan() }.getOrDefault(false)
            if (started) latch.await(timeoutMs, TimeUnit.MILLISECONDS)
            latest()
        } finally {
            runCatching { context.unregisterReceiver(receiver) }
        }
    }

    private fun toMap(results: List<ScanResult>): Map<String, Int> {
        val out = LinkedHashMap<String, Int>()
        for (r in results.sortedByDescending { it.level }) {
            val bssid = normalise(r.BSSID) ?: continue
            if (isLocallyAdministered(bssid)) continue
            out[bssid] = r.level
            if (out.size >= MAX_NETWORKS) break
        }
        return out
    }

    companion object {
        const val MAX_NETWORKS = 30

        fun normalise(bssid: String?): String? =
            bssid?.lowercase()?.takeIf { it.matches(Regex("[0-9a-f]{2}(:[0-9a-f]{2}){5}")) }

        /** Bit 1 of the first octet marks a software-assigned address (hotspots, randomised MACs). */
        fun isLocallyAdministered(bssid: String): Boolean =
            (bssid.substring(0, 2).toInt(16) and 0x02) != 0

        /** Averages several scans per network (a network missing from some scans is averaged over those it appears in). */
        fun average(scans: List<Map<String, Int>>): Map<String, Int> {
            val sums = HashMap<String, Int>()
            val counts = HashMap<String, Int>()
            for (s in scans) for ((k, v) in s) {
                sums[k] = (sums[k] ?: 0) + v
                counts[k] = (counts[k] ?: 0) + 1
            }
            return sums.mapValues { (k, v) -> Math.round(v.toDouble() / counts.getValue(k)).toInt() }
        }
    }
}
