package com.mdmesh.core.indoor

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Handler
import android.os.HandlerThread
import dagger.hilt.android.qualifiers.ApplicationContext
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.math.sqrt

/**
 * Magnetic field strength (µT). Steel and wiring in a building bend the field, so the strength differs from spot to
 * spot and helps tell neighbouring places apart. Blocks the calling (background) thread for about a second.
 */
@Singleton
class MagneticReader @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    /** Average field strength over roughly one second, or null when the phone has no magnetometer. */
    fun read(): Double? {
        val sm = context.getSystemService(Context.SENSOR_SERVICE) as? SensorManager ?: return null
        val sensor = sm.getDefaultSensor(Sensor.TYPE_MAGNETIC_FIELD) ?: return null
        val thread = HandlerThread("indoor-mag").also { it.start() }
        val done = CountDownLatch(1)
        var sum = 0.0
        var n = 0
        val listener = object : SensorEventListener {
            override fun onSensorChanged(e: SensorEvent) {
                sum += sqrt((e.values[0] * e.values[0] + e.values[1] * e.values[1] + e.values[2] * e.values[2]).toDouble())
                if (++n >= SAMPLES) done.countDown()
            }
            override fun onAccuracyChanged(s: Sensor?, accuracy: Int) = Unit
        }
        return try {
            sm.registerListener(listener, sensor, SensorManager.SENSOR_DELAY_GAME, Handler(thread.looper))
            done.await(2, TimeUnit.SECONDS)
            if (n > 0) sum / n else null
        } finally {
            sm.unregisterListener(listener)
            thread.quitSafely()
        }
    }

    private companion object { const val SAMPLES = 30 }
}
