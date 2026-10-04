package com.mdmesh.agent.service

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import com.mdmesh.core.indoor.IndoorEngine
import com.mdmesh.core.indoor.WifiScanner
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Keeps the in-store position current while the device is on a store floor plan.
 *
 *  - The step detector (a hardware sensor that costs almost nothing) feeds each detected step to the engine; the
 *    compass heading is only switched on for [HEADING_WINDOW_MS] after a step, so a device sitting still draws nothing.
 *  - Every [OBSERVE_INTERVAL_MS] the system's latest Wi-Fi scan corrects the estimate, which is how a device at rest
 *    stays pinned and how walking drift is pulled back.
 *  - The plan is re-downloaded every [RELOAD_INTERVAL_MS] so a fresh survey reaches devices without a restart.
 *
 * Does nothing at all until a floor plan exists for the customer.
 */
class IndoorTracker(
    private val context: Context,
    private val scope: CoroutineScope,
    private val engine: IndoorEngine,
    private val wifi: WifiScanner,
) {
    private val sm = context.getSystemService(Context.SENSOR_SERVICE) as? SensorManager
    private val stepSensor: Sensor? = sm?.getDefaultSensor(Sensor.TYPE_STEP_DETECTOR)
    private val headingSensor: Sensor? = sm?.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)

    @Volatile private var bearingDeg = 0.0
    @Volatile private var headingOnUntil = 0L
    private var headingRegistered = false
    private var job: Job? = null

    private val headingListener = object : SensorEventListener {
        override fun onSensorChanged(e: SensorEvent) {
            val rot = FloatArray(9)
            val ori = FloatArray(3)
            SensorManager.getRotationMatrixFromVector(rot, e.values)
            SensorManager.getOrientation(rot, ori)
            bearingDeg = (Math.toDegrees(ori[0].toDouble()) + 360.0) % 360.0
        }
        override fun onAccuracyChanged(s: Sensor?, accuracy: Int) = Unit
    }

    private val stepListener = object : SensorEventListener {
        override fun onSensorChanged(e: SensorEvent) {
            headingOnUntil = System.currentTimeMillis() + HEADING_WINDOW_MS
            ensureHeading(true)
            engine.onStep(STEP_LENGTH_M, bearingDeg)
        }
        override fun onAccuracyChanged(s: Sensor?, accuracy: Int) = Unit
    }

    fun start() {
        job?.cancel()
        job = scope.launch {
            var lastReload = 0L
            while (true) {
                val now = System.currentTimeMillis()
                if (now - lastReload > RELOAD_INTERVAL_MS) {
                    runCatching { engine.reload() }
                    lastReload = now
                }
                if (engine.hasMap()) {
                    registerSteps()
                    runCatching { engine.observe(wifi.latest()) }
                    if (now > headingOnUntil) ensureHeading(false)
                } else {
                    unregisterAll()
                }
                delay(OBSERVE_INTERVAL_MS)
            }
        }
    }

    fun stop() {
        job?.cancel()
        job = null
        unregisterAll()
    }

    private var stepsRegistered = false

    @Synchronized
    private fun registerSteps() {
        val s = stepSensor ?: return
        if (stepsRegistered) return
        stepsRegistered = runCatching { sm?.registerListener(stepListener, s, SensorManager.SENSOR_DELAY_NORMAL) }
            .getOrNull() == true
    }

    @Synchronized
    private fun ensureHeading(on: Boolean) {
        val s = headingSensor ?: return
        if (on && !headingRegistered) {
            headingRegistered = runCatching { sm?.registerListener(headingListener, s, SensorManager.SENSOR_DELAY_GAME) }
                .getOrNull() == true
        } else if (!on && headingRegistered) {
            runCatching { sm?.unregisterListener(headingListener) }
            headingRegistered = false
        }
    }

    @Synchronized
    private fun unregisterAll() {
        if (stepsRegistered) { runCatching { sm?.unregisterListener(stepListener) }; stepsRegistered = false }
        ensureHeading(false)
    }

    private companion object {
        const val STEP_LENGTH_M = 0.7
        const val HEADING_WINDOW_MS = 20_000L
        const val OBSERVE_INTERVAL_MS = 30_000L
        const val RELOAD_INTERVAL_MS = 10 * 60_000L
    }
}
