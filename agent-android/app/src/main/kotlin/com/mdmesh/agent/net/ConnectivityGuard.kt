package com.mdmesh.agent.net

import android.annotation.SuppressLint
import android.app.ActivityOptions
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.wifi.ScanResult
import android.net.wifi.WifiConfiguration
import android.net.wifi.WifiManager
import android.net.wifi.WifiNetworkSuggestion
import android.os.Build
import android.util.Log
import com.mdmesh.core.location.LocationCollector
import com.mdmesh.core.net.MotionState
import com.mdmesh.core.net.QuietHours
import com.mdmesh.core.store.GuardScheduleStore
import com.mdmesh.core.net.ConnectivityPolicy
import com.mdmesh.core.net.GuardActions
import com.mdmesh.core.net.GuardInput
import com.mdmesh.core.net.GuardState
import com.mdmesh.core.net.LockdownReleaser
import com.mdmesh.core.sync.CheckInWorker
import com.mdmesh.core.telemetry.EventLog
import com.mdmesh.policy.wifi.DpmHandle
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.util.Locale
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Keeps the tablet on the internet, and says so loudly when it cannot be.
 *
 *  - Wi-Fi is switched on at boot; if someone switches it off, it comes back after 3 minutes.
 *  - 10 minutes without internet: a full-screen "unusable without internet" message that keeps trying to reconnect.
 *    From then on the tablet also hunts for open Wi-Fi networks and logs where it is every 2 minutes.
 *  - 30 minutes: complete lockdown, saved across reboots. Only an administrator can lift it (exit password on the
 *    tablet, then a code emailed to the owner), or the console's "Release lockdown" command once it is back online.
 *
 * The rules themselves live in [ConnectivityPolicy] (pure, unit-tested). This class only does what the policy says.
 */
@Singleton
class ConnectivityGuard @Inject constructor(
    @ApplicationContext private val context: Context,
    private val eventLog: EventLog,
    private val locationCollector: LocationCollector,
    private val dpmHandle: DpmHandle,
) : LockdownReleaser {

    private val prefs = context.getSharedPreferences("mdm_connectivity_guard", Context.MODE_PRIVATE)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var loop: Job? = null
    @Volatile private var callbackRegistered = false
    private var suggestions: List<WifiNetworkSuggestion> = emptyList()
    /** The 15-second loop and the network callback both tick; one at a time. */
    private val tickLock = Mutex()

    /** Idempotent: safe to call from every service start. */
    @Synchronized
    fun start() {
        registerNetworkCallback()
        if (loop?.isActive == true) return
        loop = scope.launch {
            while (isActive) {
                runCatching { tick() }.onFailure { Log.e(TAG, "guard tick failed", it) }
                delay(TICK_MS)
            }
        }
    }

    /** Called from the boot receiver: the next tick switches Wi-Fi on whatever its state. */
    fun onBoot() {
        prefs.edit().putBoolean(K_BOOT, true).apply()
    }

    override fun release(reason: String) {
        val online = isOnline()
        prefs.edit()
            .putBoolean(K_LOCKDOWN, false)
            .putLong(K_OFFLINE_SINCE, if (online) 0L else System.currentTimeMillis())
            .putLong(K_LAST_REPORT, 0L)
            .apply()
        GuardUi.lockdownWanted = false
        GuardUi.blockWanted = false
        runCatching { eventLog.record(EVENT, "lockdown released ($reason)") }
        runCatching { CheckInWorker.scheduleNow(context) }
    }

    // ---------------------------------------------------------------------------------------- the tick

    private suspend fun tick() = tickLock.withLock {
        val now = System.currentTimeMillis()
        val wifi = context.getSystemService(WifiManager::class.java)
        val wifiOn = wifi?.isWifiEnabled ?: true
        val online = isOnline()
        val before = load()
        val quiet = QuietHours.parse(GuardScheduleStore.read(context))?.let { q ->
            val cal = java.util.Calendar.getInstance()
            q.contains(cal.get(java.util.Calendar.HOUR_OF_DAY) * 60 + cal.get(java.util.Calendar.MINUTE))
        } ?: false
        val step = ConnectivityPolicy.step(before, GuardInput(now, wifiOn, online, quiet = quiet, moved = MotionState.sustained(now),
            enabled = com.mdmesh.core.net.GuardSwitch.isEnabled(context)))
        save(step.state)
        val a = step.actions

        GuardUi.online = online
        GuardUi.offlineSince = step.state.offlineSince
        GuardUi.attempts = step.state.reconnectAttempts
        GuardUi.blockWanted = a.blockWanted
        GuardUi.lockdownWanted = a.lockdownWanted
        com.mdmesh.core.net.GuardStatus.lockdown = a.lockdownWanted

        if (a.enableWifi) enableWifi(before.wifiOffSince, now)
        if (a.reconnect) reconnect(step.state.reconnectAttempts)
        if (a.wentOnline) backOnline(before.offlineSince, now)
        if (a.enteredLockdown) runCatching { eventLog.record(EVENT, "LOCKDOWN: no internet for 30 minutes; tablet locked until an administrator unlocks it") }
        if (a.hunt) hunt()
        if (a.report) report(step.state.offlineSince, now, wifiOn)
        ensureScreen(a, now)
    }

    private fun ensureScreen(a: GuardActions, now: Long) {
        if (now < GuardUi.adminUntil) return
        when {
            a.lockdownWanted && !GuardUi.lockdownVisible -> launch(LockdownActivity::class.java)
            !a.lockdownWanted && a.blockWanted && !GuardUi.blockVisible -> launch(ConnectivityBlockActivity::class.java)
        }
    }

    private fun launch(cls: Class<*>) {
        runCatching {
            val i = Intent(context, cls).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                val options = ActivityOptions.makeBasic().apply {
                    pendingIntentBackgroundActivityStartMode = ActivityOptions.MODE_BACKGROUND_ACTIVITY_START_ALLOWED
                }
                context.startActivity(i, options.toBundle())
            } else {
                context.startActivity(i)
            }
        }.onFailure { Log.w(TAG, "could not launch " + cls.simpleName, it) }
    }

    // ---------------------------------------------------------------------------------------- doing things

    @Suppress("DEPRECATION")
    private fun enableWifi(offSince: Long?, now: Long) {
        val wifi = context.getSystemService(WifiManager::class.java) ?: return
        val ok = runCatching { wifi.setWifiEnabled(true) }.getOrDefault(false)
        val mins = offSince?.let { (now - it) / 60_000 }
        runCatching { eventLog.record(EVENT, "Wi-Fi was off${if (mins != null) " for $mins min" else ""}; switched back on (${if (ok) "ok" else "refused"})") }
    }

    @Suppress("DEPRECATION")
    private fun reconnect(attempt: Int) {
        val wifi = context.getSystemService(WifiManager::class.java) ?: return
        runCatching {
            when {
                attempt > 0 && attempt % 12 == 0 -> { wifi.setWifiEnabled(false); wifi.setWifiEnabled(true) } // radio power cycle
                attempt > 0 && attempt % 5 == 0 -> { wifi.disconnect(); wifi.reconnect() }
                else -> wifi.reconnect()
            }
        }
    }

    /** Looks for open networks and offers them to the system, which connects when one is usable. */
    @SuppressLint("MissingPermission")
    @Suppress("DEPRECATION")
    private fun hunt() {
        val wifi = context.getSystemService(WifiManager::class.java) ?: return
        // Scan results need location on; a Device Owner may switch it on.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            runCatching { dpmHandle.dpm.setLocationEnabled(dpmHandle.admin, true) }
        }
        runCatching { wifi.startScan() }
        val results = runCatching { wifi.scanResults }.getOrDefault(emptyList<ScanResult>())
        val open = results.filter { isOpen(it.capabilities) && !it.SSID.isNullOrBlank() }
            .sortedByDescending { it.level }
            .distinctBy { it.SSID }
        GuardUi.openSeen = open.size
        if (open.isEmpty()) return
        var added = "n/a"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            runCatching {
                if (suggestions.isNotEmpty()) wifi.removeNetworkSuggestions(suggestions)
                val list = open.take(MAX_SUGGESTIONS).map {
                    WifiNetworkSuggestion.Builder().setSsid(it.SSID).setIsAppInteractionRequired(false).build()
                }
                added = when (wifi.addNetworkSuggestions(list)) {
                    WifiManager.STATUS_NETWORK_SUGGESTIONS_SUCCESS -> "offered"
                    else -> "refused"
                }
                suggestions = list
            }
        } else {
            runCatching {
                for (r in open.take(MAX_SUGGESTIONS)) {
                    val cfg = WifiConfiguration().apply {
                        SSID = "\"" + r.SSID + "\""
                        allowedKeyManagement.set(WifiConfiguration.KeyMgmt.NONE)
                    }
                    val id = wifi.addNetwork(cfg)
                    if (id >= 0) wifi.enableNetwork(id, false)
                }
                added = "added"
            }
        }
        runCatching { eventLog.record(EVENT, "hunting: ${open.size} open Wi-Fi network(s) in range (" + open.take(4).joinToString { it.SSID } + "), $added") }
    }

    /** The "where is it and what is it doing" line, queued in the event log and uploaded on the first check-in that gets through. */
    private suspend fun report(offlineSince: Long?, now: Long, wifiOn: Boolean) {
        val mins = offlineSince?.let { (now - it) / 60_000 } ?: 0
        val fix = withContext(Dispatchers.IO) { runCatching { locationCollector.collect(forceActive = true) }.getOrNull() }
        val where = if (fix != null) {
            val age = ((now - fix.capturedAt) / 1000).coerceAtLeast(0)
            String.format(Locale.US, "location %.5f,%.5f ±%sm via %s (%ds old)", fix.lat, fix.lon, fix.accuracyM?.toInt() ?: "?", fix.provider ?: "?", age)
        } else {
            "no location fix"
        }
        runCatching { eventLog.record(REPORT_EVENT, "offline $mins min · $where · Wi-Fi ${if (wifiOn) "on" else "off"} · open networks seen ${GuardUi.openSeen}") }
    }

    private fun backOnline(offlineSince: Long?, now: Long) {
        val mins = offlineSince?.let { (now - it) / 60_000 } ?: 0
        runCatching { eventLog.record(EVENT, "back online after $mins min") }
        // Push the queued location reports and logs straight away.
        runCatching { CheckInWorker.scheduleNow(context) }
    }

    // ---------------------------------------------------------------------------------------- state

    private fun isOnline(): Boolean {
        val cm = context.getSystemService(ConnectivityManager::class.java) ?: return false
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }

    private fun registerNetworkCallback() {
        if (callbackRegistered) return
        callbackRegistered = true
        runCatching {
            val cm = context.getSystemService(ConnectivityManager::class.java) ?: return
            cm.registerDefaultNetworkCallback(object : ConnectivityManager.NetworkCallback() {
                override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
                    // The default network just became validated: do not wait for the next tick.
                    if (caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)) scope.launch { runCatching { tick() } }
                }
            })
        }.onFailure { callbackRegistered = false }
    }

    private fun load(): GuardState = GuardState(
        wifiOffSince = prefs.getLong(K_WIFI_OFF, 0L).takeIf { it > 0 },
        offlineSince = prefs.getLong(K_OFFLINE_SINCE, 0L).takeIf { it > 0 },
        lockdown = prefs.getBoolean(K_LOCKDOWN, false),
        bootPending = prefs.getBoolean(K_BOOT, false),
        lastEnableAt = prefs.getLong(K_LAST_ENABLE, 0L),
        lastReconnectAt = prefs.getLong(K_LAST_RECONNECT, 0L),
        lastHuntAt = prefs.getLong(K_LAST_HUNT, 0L),
        lastReportAt = prefs.getLong(K_LAST_REPORT, 0L),
        reconnectAttempts = prefs.getInt(K_ATTEMPTS, 0),
        suspended = prefs.getBoolean(K_SUSPENDED, false),
    )

    private fun save(s: GuardState) {
        prefs.edit()
            .putLong(K_WIFI_OFF, s.wifiOffSince ?: 0L)
            .putLong(K_OFFLINE_SINCE, s.offlineSince ?: 0L)
            .putBoolean(K_LOCKDOWN, s.lockdown)
            .putBoolean(K_BOOT, s.bootPending)
            .putLong(K_LAST_ENABLE, s.lastEnableAt)
            .putLong(K_LAST_RECONNECT, s.lastReconnectAt)
            .putLong(K_LAST_HUNT, s.lastHuntAt)
            .putLong(K_LAST_REPORT, s.lastReportAt)
            .putInt(K_ATTEMPTS, s.reconnectAttempts)
            .putBoolean(K_SUSPENDED, s.suspended)
            .apply()
    }

    private companion object {
        const val TAG = "ConnectivityGuard"
        const val TICK_MS = 15_000L
        const val MAX_SUGGESTIONS = 10
        const val EVENT = "connectivityChange"
        const val REPORT_EVENT = "offlineReport"
        const val K_WIFI_OFF = "wifiOffSince"
        const val K_OFFLINE_SINCE = "offlineSince"
        const val K_LOCKDOWN = "lockdown"
        const val K_BOOT = "bootPending"
        const val K_LAST_ENABLE = "lastEnableAt"
        const val K_LAST_RECONNECT = "lastReconnectAt"
        const val K_LAST_HUNT = "lastHuntAt"
        const val K_LAST_REPORT = "lastReportAt"
        const val K_ATTEMPTS = "attempts"
        const val K_SUSPENDED = "suspended"

        /** No password and no enterprise/enhanced-open encryption in the advertised capabilities. */
        fun isOpen(capabilities: String?): Boolean {
            val c = capabilities ?: return false
            return listOf("WEP", "WPA", "SAE", "PSK", "EAP", "OWE", "SUITE_B").none { c.contains(it) }
        }
    }
}
