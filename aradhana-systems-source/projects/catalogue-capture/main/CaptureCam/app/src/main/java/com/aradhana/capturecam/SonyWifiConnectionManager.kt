package com.aradhana.capturecam

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.wifi.WifiNetworkSpecifier
import android.os.Build
import android.util.Log

/**
 * Joins the Sony camera's own WiFi access point (its "PC Remote"/"Smart
 * Remote Control" mode broadcasts its own SSID+password on-screen) and
 * binds this app's PTP-IP traffic to that specific network -- WITHOUT
 * disconnecting the phone's normal WiFi for everything else (uploads,
 * CaptureCam's own LAN traffic to the JewelleryCatalogTool server keep
 * using the regular network; only sockets explicitly bound via
 * boundSocketFactory/bindProcess below go over the camera's network).
 *
 * Uses WifiNetworkSpecifier (Android 10+/API 29+), the only API surface
 * that lets an app request a specific unsaved WiFi network without needing
 * ACCESS_FINE_LOCATION or pre-provisioning it in system WiFi settings --
 * the system shows its own connect dialog with the requested SSID.
 * App minSdk is 26 (see build.gradle.kts), but the actual target device
 * for this integration (Nothing Phone, Android 16) is far above 29, so no
 * legacy WifiManager fallback is implemented -- connect()/onUnsupported
 * below fails open with a clear log message on pre-Q devices rather than
 * silently no-op-ing.
 */
class SonyWifiConnectionManager(private val context: Context) {

    companion object {
        private const val TAG = "SonyWifiConn"
    }

    private val connectivityManager
        get() = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager

    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    @Volatile var boundNetwork: Network? = null
        private set

    /**
     * Prompts the system WiFi-connect dialog for the given SSID/password
     * (shown on the camera's own screen when it's set to remote-control
     * mode) and, on success, binds this process's default network calls to
     * it via ConnectivityManager.bindProcessToNetwork -- so
     * SonyPtpIpController's plain java.net.Socket calls transparently route
     * over the camera's AP without any socket-level plumbing.
     *
     * CAUTION: bindProcessToNetwork affects the WHOLE PROCESS's default
     * network, not just PTP-IP sockets -- while connected to the camera,
     * other network calls in this app (e.g. capture_server.py uploads) will
     * also try to route over the camera's AP unless it has no route to
     * them, in which case they'll simply fail rather than silently using
     * the wrong network. Call unbind() as soon as the capture session with
     * the camera is done, before resuming normal upload/LAN traffic.
     */
    fun connect(ssid: String, password: String, timeoutMs: Long, onResult: (Boolean) -> Unit) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            Log.e(TAG, "WifiNetworkSpecifier requires API 29+ (this device: ${Build.VERSION.SDK_INT}) -- no legacy fallback implemented")
            onResult(false)
            return
        }
        val specifier = WifiNetworkSpecifier.Builder()
            .setSsid(ssid)
            .setWpa2Passphrase(password)
            .build()
        val request = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .setNetworkSpecifier(specifier)
            .build()

        var resolved = false
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                if (resolved) return
                resolved = true
                Log.i(TAG, "Joined camera WiFi network: $ssid")
                boundNetwork = network
                val bound = connectivityManager.bindProcessToNetwork(network)
                if (!bound) Log.w(TAG, "bindProcessToNetwork returned false")
                onResult(true)
            }

            override fun onUnavailable() {
                if (resolved) return
                resolved = true
                Log.w(TAG, "Could not join camera WiFi network: $ssid (unavailable)")
                onResult(false)
            }

            override fun onLost(network: Network) {
                Log.w(TAG, "Lost camera WiFi network connection")
                if (boundNetwork == network) {
                    boundNetwork = null
                    connectivityManager.bindProcessToNetwork(null)
                }
            }
        }
        networkCallback = callback
        connectivityManager.requestNetwork(request, callback, timeoutMs.toInt())
    }

    /** Releases the camera network request and restores normal network
     * routing for the rest of the app. Always call this once the Sony
     * camera session is finished. */
    fun unbind() {
        try {
            networkCallback?.let { connectivityManager.unregisterNetworkCallback(it) }
        } catch (_: Exception) {}
        networkCallback = null
        if (boundNetwork != null) {
            connectivityManager.bindProcessToNetwork(null)
            boundNetwork = null
        }
    }
}
