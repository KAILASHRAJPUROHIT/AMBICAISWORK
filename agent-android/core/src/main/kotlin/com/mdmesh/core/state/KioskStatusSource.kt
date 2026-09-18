package com.mdmesh.core.state

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import android.os.BatteryManager

/** A single read of "what a kiosk status bar shows right now" — battery percent/charging and
 *  Wi-Fi connection/signal. Deliberately synchronous and receiver-free (unlike
 *  [DeviceStateCollector], which is check-in telemetry on its own cadence): a kiosk status bar
 *  polls this on a short timer of its own, independent of the check-in cycle. */
object KioskStatusSource {

    data class Status(val batteryPct: Int, val charging: Boolean, val wifiConnected: Boolean, val wifiBars: Int)

    fun read(context: Context): Status {
        val batt = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = batt?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = batt?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        val status = batt?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val charging = status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL

        var wifiConnected = false
        var wifiBars = 0
        runCatching {
            val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
            val caps = cm?.activeNetwork?.let { cm.getNetworkCapabilities(it) }
            wifiConnected = caps?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true
            if (wifiConnected) {
                @Suppress("DEPRECATION") // no non-deprecated RSSI read without location permission + scan API
                val wm = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
                @Suppress("DEPRECATION")
                val rssi = wm?.connectionInfo?.rssi
                wifiBars = if (rssi != null) WifiManager.calculateSignalLevel(rssi, 5) else 0
            }
        }

        return Status(
            batteryPct = DeviceStateCollector.batteryPercent(level, scale),
            charging = charging,
            wifiConnected = wifiConnected,
            wifiBars = wifiBars,
        )
    }
}
