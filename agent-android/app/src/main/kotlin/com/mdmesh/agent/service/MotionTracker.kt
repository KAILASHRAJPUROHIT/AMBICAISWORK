package com.mdmesh.agent.service

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorManager
import android.hardware.TriggerEvent
import android.hardware.TriggerEventListener
import android.util.Log
import com.mdmesh.core.location.LocationCollector
import com.mdmesh.core.sync.CheckInCoordinator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Reports location more often only while the device is actually moving.
 *
 * Uses the hardware "significant motion" trigger sensor, which costs essentially no battery while the device sits
 * still. Each trigger opens (or extends) a [MOVING_WINDOW_MS] window during which, every [MOVING_INTERVAL_MS], a fresh
 * network fix is taken and a check-in is run so the trail and geofences follow the device. When the window lapses the
 * agent returns to the normal 15-minute check-in. Devices without the sensor simply keep the normal cadence.
 */
class MotionTracker(
    private val context: Context,
    private val scope: CoroutineScope,
    private val collector: LocationCollector,
    private val coordinator: CheckInCoordinator,
) {
    private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as? SensorManager
    private val sensor: Sensor? = sensorManager?.getDefaultSensor(Sensor.TYPE_SIGNIFICANT_MOTION)

    @Volatile private var movingUntil = 0L
    private var loop: Job? = null
    private var armed = false

    private val listener = object : TriggerEventListener() {
        override fun onTrigger(event: TriggerEvent?) {
            armed = false // trigger sensors are one-shot
            movingUntil = System.currentTimeMillis() + MOVING_WINDOW_MS
            startLoop()
            arm()
        }
    }

    fun start() = arm()

    fun stop() {
        runCatching { if (armed) sensorManager?.cancelTriggerSensor(listener, sensor) }
        armed = false
        loop?.cancel()
        loop = null
    }

    @Synchronized
    private fun arm() {
        val sm = sensorManager ?: return
        val s = sensor ?: return
        if (armed) return
        armed = runCatching { sm.requestTriggerSensor(listener, s) }.getOrDefault(false)
    }

    @Synchronized
    private fun startLoop() {
        if (loop?.isActive == true) return
        loop = scope.launch {
            while (System.currentTimeMillis() < movingUntil) {
                runCatching { collector.refresh() }
                runCatching { coordinator.runOnce() }.onFailure { Log.w(TAG, "moving check-in failed", it) }
                delay(MOVING_INTERVAL_MS)
            }
        }
    }

    private companion object {
        const val TAG = "MotionTracker"
        const val MOVING_WINDOW_MS = 10 * 60_000L
        const val MOVING_INTERVAL_MS = 2 * 60_000L
    }
}
