package com.aradhana.capturecam

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.provider.Settings
import android.util.Log
import androidx.work.BackoffPolicy
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.Constraints
import androidx.work.workDataOf
import java.net.HttpURLConnection
import java.net.Inet4Address
import java.net.URL
import java.util.concurrent.TimeUnit
import javax.net.ssl.HttpsURLConnection
import kotlin.coroutines.resume
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject

/**
 * Keeps the laptop able to reach this tablet over wireless ADB after every
 * reboot without anyone reading a port off the Wireless-debugging screen.
 *
 * Android picks a NEW random TLS port each time Wireless debugging starts and
 * shell cannot pin it, so: (1) switch Wireless debugging back on (needs
 * WRITE_SECURE_SETTINGS, granted once with `adb shell pm grant`, which
 * survives reboots), (2) find our own adb TLS port, (3) tell the capture
 * server "ip:port", which the laptop's tablet watcher reads and connects to.
 * Runs at boot, on every app launch, and every 15 minutes thereafter.
 */
object TabletAdbBeacon {
    private const val TAG = "TabletAdbBeacon"
    private const val WORK_NOW = "tablet_adb_beacon_now"
    private const val WORK_PERIODIC = "tablet_adb_beacon_periodic"

    fun schedule(context: Context, reason: String) {
        val app = context.applicationContext
        val wm = WorkManager.getInstance(app)
        val net = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
        wm.enqueueUniqueWork(
            WORK_NOW, ExistingWorkPolicy.REPLACE,
            OneTimeWorkRequestBuilder<BeaconWorker>()
                .setConstraints(net)
                .setBackoffCriteria(BackoffPolicy.LINEAR, 30, TimeUnit.SECONDS)
                .setInputData(workDataOf("reason" to reason))
                .build()
        )
        wm.enqueueUniquePeriodicWork(
            WORK_PERIODIC, ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<BeaconWorker>(15, TimeUnit.MINUTES)
                .setConstraints(net)
                .setInputData(workDataOf("reason" to "periodic"))
                .build()
        )
    }

    class BootReceiver : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            schedule(context, "boot")
        }
    }

    class BeaconWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
        override suspend fun doWork(): Result {
            val reason = inputData.getString("reason") ?: "work"
            return if (beacon(applicationContext, reason)) Result.success() else Result.retry()
        }
    }

    private fun ensureWirelessDebugging(context: Context) {
        if (context.checkSelfPermission(Manifest.permission.WRITE_SECURE_SETTINGS) != PackageManager.PERMISSION_GRANTED) {
            Log.w(TAG, "WRITE_SECURE_SETTINGS not granted - run: adb shell pm grant ${context.packageName} android.permission.WRITE_SECURE_SETTINGS")
            return
        }
        try {
            val cr = context.contentResolver
            if (Settings.Global.getInt(cr, "adb_wifi_enabled", 0) != 1) {
                Settings.Global.putInt(cr, "adb_wifi_enabled", 1)
                Log.i(TAG, "Wireless debugging switched on")
            }
        } catch (e: Exception) {
            Log.w(TAG, "could not enable wireless debugging: ${e.message}")
        }
    }

    private fun ownWifiIp(context: Context): String? {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return null
        val net = cm.activeNetwork ?: return null
        return cm.getLinkProperties(net)?.linkAddresses
            ?.firstOrNull { it.address is Inet4Address && !it.address.isLoopbackAddress }
            ?.address?.hostAddress
    }

    private fun tlsPortFromProperty(): Int = try {
        val p = Runtime.getRuntime().exec(arrayOf("getprop", "service.adb.tls.port"))
        p.inputStream.bufferedReader().readText().trim().toIntOrNull() ?: 0
    } catch (_: Exception) { 0 }

    /** Our own adb TLS service via mDNS - the reliable route on Android 11+. */
    private suspend fun tlsPortFromNsd(context: Context, ownIp: String?): Int =
        withTimeoutOrNull(8_000) {
            suspendCancellableCoroutine { cont ->
                val nsd = context.getSystemService(Context.NSD_SERVICE) as NsdManager
                lateinit var listener: NsdManager.DiscoveryListener
                var done = false
                fun finish(port: Int) {
                    if (done) return
                    done = true
                    try { nsd.stopServiceDiscovery(listener) } catch (_: Exception) {}
                    if (cont.isActive) cont.resume(port)
                }
                listener = object : NsdManager.DiscoveryListener {
                    override fun onDiscoveryStarted(serviceType: String) {}
                    override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) = finish(0)
                    override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {}
                    override fun onDiscoveryStopped(serviceType: String) {}
                    override fun onServiceLost(serviceInfo: NsdServiceInfo) {}
                    @Suppress("DEPRECATION")
                    override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                        nsd.resolveService(serviceInfo, object : NsdManager.ResolveListener {
                            override fun onResolveFailed(si: NsdServiceInfo, errorCode: Int) {}
                            override fun onServiceResolved(si: NsdServiceInfo) {
                                val host = si.host?.hostAddress
                                if (ownIp == null || host == ownIp) finish(si.port)
                            }
                        })
                    }
                }
                nsd.discoverServices("_adb-tls-connect._tcp", NsdManager.PROTOCOL_DNS_SD, listener)
                cont.invokeOnCancellation { finish(0) }
            }
        } ?: 0

    private fun post(baseUrl: String, body: JSONObject): Boolean = try {
        val conn = URL(baseUrl.trimEnd('/') + "/api/tablet/adb_endpoint").openConnection() as HttpURLConnection
        if (conn is HttpsURLConnection) {
            conn.sslSocketFactory = ServerDiscovery.trustAllSocketFactory
            conn.hostnameVerifier = javax.net.ssl.HostnameVerifier { _, _ -> true }
        }
        conn.connectTimeout = 4_000
        conn.readTimeout = 6_000
        conn.requestMethod = "POST"
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "application/json")
        conn.outputStream.use { it.write(body.toString().toByteArray()) }
        val ok = conn.responseCode in 200..299
        conn.disconnect()
        ok
    } catch (e: Exception) {
        Log.w(TAG, "report to $baseUrl failed: ${e.message}")
        false
    }

    suspend fun beacon(context: Context, reason: String): Boolean = withContext(Dispatchers.IO) {
        ensureWirelessDebugging(context)
        val ip = ownWifiIp(context) ?: return@withContext false
        var port = tlsPortFromProperty()
        if (port <= 0) port = tlsPortFromNsd(context, ip)
        if (port <= 0 && reason == "boot") {
            // Wireless debugging can be flagged on yet not listening right after
            // boot (Wi-Fi came up late): bounce it once. Only at boot -- doing
            // this on app launch / periodic runs would drop a live ADB session.
            try {
                val cr = context.contentResolver
                Settings.Global.putInt(cr, "adb_wifi_enabled", 0)
                kotlinx.coroutines.delay(1_500)
                Settings.Global.putInt(cr, "adb_wifi_enabled", 1)
                kotlinx.coroutines.delay(2_500)
            } catch (_: Exception) {}
            port = tlsPortFromProperty()
            if (port <= 0) port = tlsPortFromNsd(context, ip)
        }
        if (port <= 0) {
            // Normal while adbd is in fixed tcpip:5555 mode (no TLS listener);
            // the laptop is already connected then, so don't retry-storm.
            Log.w(TAG, "no adb TLS port visible ($reason)")
            return@withContext reason != "boot"
        }
        val prefs = context.getSharedPreferences("capturecam", Context.MODE_PRIVATE)
        val configured = prefs.getString("server_url", null)?.trim()?.ifEmpty { null } ?: "https://ARADHANA.local:7660"
        val body = JSONObject()
            .put("ip", ip).put("port", port).put("reason", reason)
            .put("device", android.os.Build.MODEL ?: "")
        val resolved = try { UploadClient.resolveDeliveryBaseUrl(context, configured) } catch (_: Exception) { configured }
        val ok = post(resolved, body) || (resolved != configured && post(configured, body))
        Log.i(TAG, "beacon $ip:$port ($reason) -> ${if (ok) "reported" else "server unreachable"}")
        ok
    }
}
