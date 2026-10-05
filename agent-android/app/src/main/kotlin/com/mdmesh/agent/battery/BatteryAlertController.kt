package com.mdmesh.agent.battery

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import com.mdmesh.core.battery.BatteryStage
import com.mdmesh.core.battery.BatteryStagePolicy
import com.mdmesh.core.battery.BatteryUi
import com.mdmesh.core.telemetry.EventLog

/**
 * Watches the battery for as long as the agent service runs: publishes the stage for the coloured screen border, and plays the
 * warning when the battery drops into a worse stage (30, 20 and 10%) and every 2 minutes while it stays at 10% or below.
 * Nothing plays while the screen is off, or while the tablet is charging.
 */
class BatteryAlertController(private val context: Context, private val events: EventLog) {
    private val main = Handler(Looper.getMainLooper())
    private val player = BatteryAlertPlayer(context)
    private var previous: BatteryStage? = null
    private var started = false

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(c: Context?, i: Intent?) {
            val level = i?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
            val scale = i?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
            val status = i?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
            val pct = if (level >= 0 && scale > 0) level * 100 / scale else -1
            val charging = status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL
            onReading(pct, charging)
        }
    }

    private val repeat = object : Runnable {
        override fun run() {
            if (BatteryUi.stage == BatteryStage.RED) {
                if (screenOn()) player.play(BatteryStage.RED)
                main.postDelayed(this, BatteryStagePolicy.RED_REPEAT_MS)
            }
        }
    }

    fun start() {
        if (started) return
        started = true
        context.registerReceiver(receiver, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
    }

    fun stop() {
        if (!started) return
        started = false
        runCatching { context.unregisterReceiver(receiver) }
        main.removeCallbacks(repeat)
    }

    private fun onReading(pct: Int, charging: Boolean) {
        val before = previous
        val now = BatteryStagePolicy.stageOf(pct, charging)
        BatteryUi.update(pct, charging)
        previous = now
        if (BatteryStagePolicy.shouldAnnounce(before, now)) {
            runCatching { events.record("lowBattery", "battery $pct%: $now") }
            if (screenOn()) player.play(now) // screen off: do nothing
        }
        main.removeCallbacks(repeat)
        if (now == BatteryStage.RED) main.postDelayed(repeat, BatteryStagePolicy.RED_REPEAT_MS)
    }

    private fun screenOn(): Boolean =
        (context.getSystemService(Context.POWER_SERVICE) as? PowerManager)?.isInteractive ?: true
}
