package com.mdmesh.agent.service

import android.app.Activity
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.display.DisplayManager
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.DisplayMetrics
import android.util.Log
import android.view.WindowManager
import androidx.core.app.NotificationCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import com.mdmesh.agent.R
import com.mdmesh.core.remote.LiveFrameUploader
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Live screen share: MediaProjection -> VirtualDisplay -> hardware H.264 encoder (surface input)
 * -> framed packets batched every ~66 ms -> server relay -> browser (WebCodecs).
 *
 * 30 fps, ~4 Mbps at up to 1280 px on the long edge, a keyframe every second so a viewer can join
 * quickly. If the uplink backs up, queued video is dropped and a fresh keyframe requested rather
 * than letting latency grow. Rotation rebuilds the encoder at the new shape.
 *
 * Packet framing: type(1: 1=config, 2=key, 3=delta) | ptsUs(8, BE) | length(4, BE) | payload.
 */
@AndroidEntryPoint
class LiveScreenService : LifecycleService() {
    @Inject lateinit var uploader: LiveFrameUploader

    private var projection: MediaProjection? = null
    private var job: Job? = null
    private val handler = Handler(Looper.getMainLooper())

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED) ?: Activity.RESULT_CANCELED
        val data = intent?.let {
            if (Build.VERSION.SDK_INT >= 33) it.getParcelableExtra(EXTRA_DATA, Intent::class.java) else @Suppress("DEPRECATION") it.getParcelableExtra(EXTRA_DATA)
        }
        val durationSec = intent?.getIntExtra(EXTRA_DURATION, 300) ?: 300
        if (resultCode != Activity.RESULT_OK || data == null) {
            stopSelf(); return START_NOT_STICKY
        }
        if (!runCatching { startForegroundNow() }.onFailure { Log.e(TAG, "startForeground failed", it) }.isSuccess) {
            stopSelf(); return START_NOT_STICKY
        }
        val mpm = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        val mp = runCatching { mpm.getMediaProjection(resultCode, data) }.getOrNull()
        if (mp == null) { stopSelf(); return START_NOT_STICKY }
        projection = mp
        mp.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() { handler.post { stopSelf() } }
        }, handler)

        job?.cancel()
        job = lifecycleScope.launch(kotlinx.coroutines.Dispatchers.Default) {
            runCatching { runStream(mp, durationSec) }.onFailure { Log.e(TAG, "live stream ended with error", it) }
            handler.post { stopSelf() }
        }
        return START_NOT_STICKY
    }

    private suspend fun runStream(mp: MediaProjection, durationSec: Int) = kotlinx.coroutines.coroutineScope {
        val pump = LiveEncoderPump("screen", uploader, FPS, BITRATE)
        pump.startSender(this)
        var size = targetSize()
        var display = mp.createVirtualDisplay(
            "mdm-live", size.first, size.second, resources.displayMetrics.densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, pump.open(size.first, size.second), null, handler,
        )
        val until = System.currentTimeMillis() + durationSec.coerceIn(30, 1800) * 1000L
        var lastSizeCheck = 0L
        while (isActive && System.currentTimeMillis() < until) {
            val now = System.currentTimeMillis()
            if (now - lastSizeCheck > 1000) { // follow rotation
                lastSizeCheck = now
                val s = targetSize()
                if (s != size) {
                    size = s
                    runCatching { display.release() }
                    pump.close()
                    display = mp.createVirtualDisplay(
                        "mdm-live", s.first, s.second, resources.displayMetrics.densityDpi,
                        DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, pump.open(s.first, s.second), null, handler,
                    )
                }
            }
            pump.drainOnce()
        }
        runCatching { display.release() }
        pump.stop()
    }

    /** Long edge capped at 1280 px, aspect kept, both sides multiples of 16 (hardware encoders want that). */
    private fun targetSize(): Pair<Int, Int> {
        val dm = DisplayMetrics()
        @Suppress("DEPRECATION")
        (getSystemService(Context.WINDOW_SERVICE) as WindowManager).defaultDisplay.getRealMetrics(dm)
        val long = maxOf(dm.widthPixels, dm.heightPixels).toFloat()
        val scale = (LONG_EDGE / long).coerceAtMost(1f)
        val w = ((dm.widthPixels * scale).toInt() / 16 * 16).coerceAtLeast(16)
        val h = ((dm.heightPixels * scale).toInt() / 16 * 16).coerceAtLeast(16)
        return w to h
    }

    private fun startForegroundNow() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && manager.getNotificationChannel(CHANNEL_ID) == null) {
            manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "Remote management", NotificationManager.IMPORTANCE_LOW))
        }
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle("AMBIC MDM live session")
            .setContentText("Live screen share is active")
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    override fun onDestroy() {
        job?.cancel()
        runCatching { projection?.stop() }
        projection = null
        super.onDestroy()
    }

    companion object {
        private const val TAG = "LiveScreenService"
        private const val CHANNEL_ID = "mdm_remote_capture"
        private const val NOTIFICATION_ID = 1003
        private const val EXTRA_RESULT_CODE = "resultCode"
        private const val EXTRA_DATA = "data"
        private const val EXTRA_DURATION = "durationSec"
        private const val LONG_EDGE = 1280f
        private const val FPS = 60
        private const val BITRATE = 8_000_000

        fun intent(context: Context, resultCode: Int, data: Intent, durationSec: Int): Intent =
            Intent(context, LiveScreenService::class.java)
                .putExtra(EXTRA_RESULT_CODE, resultCode)
                .putExtra(EXTRA_DATA, data)
                .putExtra(EXTRA_DURATION, durationSec)
    }
}
