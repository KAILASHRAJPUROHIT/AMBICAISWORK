package com.mdmesh.policy.wifi

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.wifi.WifiManager
import android.os.SystemClock
import android.util.Log
import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.ReadableTogglePolicy

/**
 * Wi-Fi radio on/off for the Quick Controls panel (and `policy.apply` key `wifiRadio`).
 *
 * `WifiManager.setWifiEnabled` is blocked for apps targeting Android 10+, but a Device Owner is
 * explicitly exempt -- AOSP `WifiServiceImpl.setWifiEnabled` only rejects callers that are not
 * privileged, not DO/PO, and not system. It needs only the normal CHANGE_WIFI_STATE permission,
 * no AppOp, so unlike auto-rotate it survives agent updates. It still refuses in airplane mode.
 *
 * These tablets are Wi-Fi only: while Wi-Fi is off the MDM server and the shop PC's ADB watchers
 * cannot reach the device. So turning it OFF always arms [WifiAutoRestore] to switch it back on
 * after [AUTO_RESTORE_MS] (3 minutes, agreed 2026-09-28) -- whether the off came from the panel or
 * a remote policy.apply. Turning it ON cancels the pending restore.
 */
interface WifiRadioPolicy : ReadableTogglePolicy {
    companion object {
        const val CAPABILITY_KEY = "wifiRadio"
        const val AUTO_RESTORE_MS = 3 * 60_000L
    }
}

object WifiRadioPolicyFactory {
    fun create(handle: DpmHandle): WifiRadioPolicy? =
        WifiRadioToggle(handle).takeIf { it.isSupported() }
}

internal class WifiRadioToggle(private val handle: DpmHandle) : WifiRadioPolicy {

    override val capabilityKey: String = WifiRadioPolicy.CAPABILITY_KEY

    private val wifi: WifiManager? =
        handle.context.applicationContext.getSystemService(WifiManager::class.java)

    override fun isSupported(): Boolean =
        wifi != null && runCatching { handle.dpm.isDeviceOwnerApp(handle.admin.packageName) }.getOrDefault(false)

    @Suppress("DEPRECATION") // deprecated for ordinary apps; Device Owner is exempt (see class doc)
    override fun setEnabled(enabled: Boolean): PolicyOutcome {
        val wm = wifi ?: return PolicyOutcome.Unsupported
        val ok = runCatching { wm.setWifiEnabled(enabled) }.getOrDefault(false)
        if (!ok) return PolicyOutcome.Failed("setWifiEnabled($enabled) refused (airplane mode?)")
        if (enabled) {
            WifiAutoRestore.cancel(handle.context)
        } else {
            WifiAutoRestore.schedule(handle.context, WifiRadioPolicy.AUTO_RESTORE_MS)
        }
        return PolicyOutcome.Applied
    }

    override fun isEnabled(): Boolean? = runCatching { wifi?.isWifiEnabled }.getOrNull()
}

/** Doze-tolerant one-shot "turn Wi-Fi back on" alarm. Uses setAndAllowWhileIdle like
 *  WakeKeepAlive: no exact-alarm permission needed; on time while the tablet is awake or
 *  charging, at the next maintenance window at worst in deep Doze. */
object WifiAutoRestore {

    private const val REQUEST_CODE = 0x57_1F1 // arbitrary, unique to this alarm

    fun schedule(context: Context, delayMs: Long) {
        val am = context.getSystemService(AlarmManager::class.java) ?: return
        runCatching {
            am.setAndAllowWhileIdle(
                AlarmManager.ELAPSED_REALTIME_WAKEUP,
                SystemClock.elapsedRealtime() + delayMs,
                pendingIntent(context),
            )
        }
    }

    fun cancel(context: Context) {
        val am = context.getSystemService(AlarmManager::class.java) ?: return
        runCatching { am.cancel(pendingIntent(context)) }
    }

    private fun pendingIntent(context: Context): PendingIntent =
        PendingIntent.getBroadcast(
            context.applicationContext,
            REQUEST_CODE,
            Intent(context.applicationContext, WifiAutoRestoreReceiver::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
}

/** Declared in the app manifest (the :policy manifest stays component-free by convention). */
class WifiAutoRestoreReceiver : BroadcastReceiver() {
    @Suppress("DEPRECATION")
    override fun onReceive(context: Context, intent: Intent) {
        val wm = context.applicationContext.getSystemService(WifiManager::class.java) ?: return
        if (wm.isWifiEnabled) return
        val ok = runCatching { wm.setWifiEnabled(true) }.getOrDefault(false)
        Log.i("WifiAutoRestore", "auto-restoring Wi-Fi after manual off: $ok")
    }
}
