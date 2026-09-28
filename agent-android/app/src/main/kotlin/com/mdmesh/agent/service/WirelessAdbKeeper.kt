package com.mdmesh.agent.service

import android.content.Context
import android.database.ContentObserver
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import com.mdmesh.policy.wifi.DpmHandle
import com.mdmesh.policy.wifi.WirelessAdbEnabler

/**
 * Keeps "Wireless debugging" on while the device is on Wi-Fi, so the shop's
 * wireless-adb-reconnect.py / appop-guardian.py can always reach it.
 *
 * Why it goes off (stock AOSP, not an OEM patch -- AdbDebuggingManager.java):
 *  - any Wi-Fi disconnect ("Network disconnected. Disabling adbwifi.") -- idle Wi-Fi drops,
 *    AP restarts, roaming;
 *  - boot: AdbService.systemReady() restores it from persist.adb.tls_server.enable, which the
 *    last disconnect already cleared;
 *  - an enable is only honored when currently on Wi-Fi AND that network is in the trusted list
 *    (verifyWifiNetwork) -- otherwise it's reset to 0 immediately.
 *
 * So the fix is to re-assert it whenever we're on Wi-Fi and it's 0, not only at boot. Verified
 * 2026-09-28: on the shop's already-trusted network, a Device-Owner setGlobalSetting enable
 * sticks (TAB PRO recovered remotely via device.enableWirelessAdb, no touch).
 *
 * Loop guard: on an untrusted network our write would be reset at once, the observer would fire,
 * and we'd retry forever. Attempts are capped per Wi-Fi connection and rate-limited; the cap
 * resets only when a new Wi-Fi network comes up.
 */
class WirelessAdbKeeper(
    private val context: Context,
    private val dpm: DpmHandle,
) {
    private val handler = Handler(Looper.getMainLooper())
    private val cm = context.getSystemService(ConnectivityManager::class.java)
    private var attemptsThisConnection = 0
    private var lastAttemptAt = 0L
    private var running = false

    private val observer = object : ContentObserver(handler) {
        override fun onChange(selfChange: Boolean) = schedule(0L)
    }

    private val wifiCallback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) {
            attemptsThisConnection = 0
            // Give AdbDebuggingManager a moment to see the new BSSID before we ask.
            schedule(SETTLE_MS)
        }
    }

    fun start() {
        if (running) return
        running = true
        runCatching {
            context.contentResolver.registerContentObserver(
                Settings.Global.getUriFor(ADB_WIFI_ENABLED), false, observer,
            )
        }
        runCatching {
            cm?.registerNetworkCallback(
                NetworkRequest.Builder().addTransportType(NetworkCapabilities.TRANSPORT_WIFI).build(),
                wifiCallback,
            )
        }
        schedule(SETTLE_MS)
    }

    fun stop() {
        if (!running) return
        running = false
        handler.removeCallbacksAndMessages(null)
        runCatching { context.contentResolver.unregisterContentObserver(observer) }
        runCatching { cm?.unregisterNetworkCallback(wifiCallback) }
    }

    /** One-shot check, safe to call from anywhere (periodic worker, boot). */
    fun checkNow() = ensureEnabled()

    private fun schedule(delayMs: Long) {
        handler.removeCallbacks(check)
        handler.postDelayed(check, delayMs)
    }

    private val check = Runnable { ensureEnabled() }

    private fun ensureEnabled() {
        if (isEnabled() || !onWifi()) return
        val now = System.currentTimeMillis()
        if (attemptsThisConnection >= MAX_ATTEMPTS_PER_CONNECTION) return
        if (now - lastAttemptAt < MIN_INTERVAL_MS) {
            schedule(MIN_INTERVAL_MS - (now - lastAttemptAt))
            return
        }
        attemptsThisConnection++
        lastAttemptAt = now
        val ok = WirelessAdbEnabler.tryEnable(dpm)
        Log.i(TAG, "wireless-adb re-enable attempt $attemptsThisConnection: dpmCall=$ok")
    }

    private fun isEnabled(): Boolean =
        runCatching { Settings.Global.getInt(context.contentResolver, ADB_WIFI_ENABLED, 0) == 1 }
            .getOrDefault(false)

    private fun onWifi(): Boolean = runCatching {
        val caps = cm?.getNetworkCapabilities(cm.activeNetwork) ?: return false
        caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
    }.getOrDefault(false)

    private companion object {
        const val TAG = "WirelessAdbKeeper"
        const val ADB_WIFI_ENABLED = "adb_wifi_enabled" // hidden SDK constant, see WirelessAdbEnabler
        const val SETTLE_MS = 3_000L
        const val MIN_INTERVAL_MS = 20_000L
        const val MAX_ATTEMPTS_PER_CONNECTION = 3
    }
}
