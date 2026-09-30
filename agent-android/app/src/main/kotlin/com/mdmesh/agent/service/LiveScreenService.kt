package com.mdmesh.agent.service

import android.app.Activity
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
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
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.ByteArrayOutputStream
import javax.inject.Inject

/**
 * Live screen share: MediaProjection -> VirtualDisplay -> ImageReader -> JPEG -> server relay.
 * Targets ~12 fps at 1024 px wide. Unchanged frames are not re-sent (a keep-alive goes out every
 * 2 s) so an idle screen costs almost nothing. The newest frame always wins - a slow uplink drops
 * frames instead of building latency.
 */
@AndroidEntryPoint
class LiveScreenService : LifecycleService() {
    @Inject lateinit var uploader: LiveFrameUploader

    private var projection: MediaProjection? = null
    private var display: VirtualDisplay? = null
    private var reader: ImageReader? = null
    private var job: Job? = null
    private var sendJob: Job? = null
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
        job = lifecycleScope.launch { runCapture(mp, durationSec) }
        return START_NOT_STICKY
    }

    private suspend fun runCapture(mp: MediaProjection, durationSec: Int) {
        val frames = Channel<ByteArray>(Channel.CONFLATED)
        sendJob = lifecycleScope.launch {
            for (bytes in frames) {
                runCatching { uploader.upload(bytes) }
            }
        }
        var size = targetSize()
        var dpi = resources.displayMetrics.densityDpi
        var localReader = ImageReader.newInstance(size.first, size.second, PixelFormat.RGBA_8888, 2)
        reader = localReader
        display = mp.createVirtualDisplay(
            "mdm-live", size.first, size.second, dpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, localReader.surface, null, handler,
        )
        val until = System.currentTimeMillis() + durationSec.coerceIn(30, 1800) * 1000L
        var lastHash = 0
        var lastSentAt = 0L
        var lastSizeCheck = 0L
        val out = ByteArrayOutputStream(96 * 1024)
        var padded: Bitmap? = null
        while (currentCoroutineContext().isActive && System.currentTimeMillis() < until) {
            val now = System.currentTimeMillis()
            if (now - lastSizeCheck > 1000) { // follow rotation
                lastSizeCheck = now
                val s = targetSize()
                if (s != size) {
                    size = s
                    dpi = resources.displayMetrics.densityDpi
                    val fresh = ImageReader.newInstance(size.first, size.second, PixelFormat.RGBA_8888, 2)
                    display?.resize(size.first, size.second, dpi)
                    display?.surface = fresh.surface
                    localReader.close()
                    localReader = fresh
                    reader = fresh
                    padded?.recycle(); padded = null
                }
            }
            val image = runCatching { localReader.acquireLatestImage() }.getOrNull()
            if (image == null) { delay(30); continue }
            try {
                val plane = image.planes[0]
                val rowPixels = plane.rowStride / plane.pixelStride
                var bmp = padded
                if (bmp == null || bmp.width != rowPixels || bmp.height != image.height) {
                    bmp?.recycle()
                    bmp = Bitmap.createBitmap(rowPixels, image.height, Bitmap.Config.ARGB_8888)
                    padded = bmp
                }
                plane.buffer.rewind()
                bmp.copyPixelsFromBuffer(plane.buffer)
                val cropped = if (rowPixels == image.width) bmp else Bitmap.createBitmap(bmp, 0, 0, image.width, image.height)
                out.reset()
                cropped.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out)
                if (cropped !== bmp) cropped.recycle()
                val bytes = out.toByteArray()
                val hash = bytes.contentHashCode()
                if (hash != lastHash || now - lastSentAt > 2000) {
                    lastHash = hash
                    lastSentAt = now
                    frames.trySend(bytes)
                }
            } finally {
                image.close()
            }
            delay(FRAME_INTERVAL_MS)
        }
        frames.close()
        stopSelf()
    }

    /** 1024 px on the long edge, aspect preserved, even numbers (encoders and VirtualDisplay like that). */
    private fun targetSize(): Pair<Int, Int> {
        val dm = DisplayMetrics()
        @Suppress("DEPRECATION")
        (getSystemService(Context.WINDOW_SERVICE) as WindowManager).defaultDisplay.getRealMetrics(dm)
        val long = maxOf(dm.widthPixels, dm.heightPixels).toFloat()
        val scale = (LONG_EDGE / long).coerceAtMost(1f)
        val w = (dm.widthPixels * scale).toInt() and 1.inv()
        val h = (dm.heightPixels * scale).toInt() and 1.inv()
        return w.coerceAtLeast(2) to h.coerceAtLeast(2)
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
        sendJob?.cancel()
        runCatching { display?.release() }
        runCatching { reader?.close() }
        runCatching { projection?.stop() }
        display = null; reader = null; projection = null
        super.onDestroy()
    }

    companion object {
        private const val TAG = "LiveScreenService"
        private const val CHANNEL_ID = "mdm_remote_capture"
        private const val NOTIFICATION_ID = 1003
        private const val EXTRA_RESULT_CODE = "resultCode"
        private const val EXTRA_DATA = "data"
        private const val EXTRA_DURATION = "durationSec"
        private const val LONG_EDGE = 1024f
        private const val JPEG_QUALITY = 50
        private const val FRAME_INTERVAL_MS = 60L

        fun intent(context: Context, resultCode: Int, data: Intent, durationSec: Int): Intent =
            Intent(context, LiveScreenService::class.java)
                .putExtra(EXTRA_RESULT_CODE, resultCode)
                .putExtra(EXTRA_DATA, data)
                .putExtra(EXTRA_DURATION, durationSec)
    }
}
