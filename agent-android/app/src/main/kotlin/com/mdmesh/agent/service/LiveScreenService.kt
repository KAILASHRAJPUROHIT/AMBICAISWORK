package com.mdmesh.agent.service

import android.app.Activity
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.DisplayMetrics
import android.util.Log
import android.view.Surface
import android.view.WindowManager
import androidx.core.app.NotificationCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import com.mdmesh.agent.R
import com.mdmesh.core.remote.LiveFrameUploader
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicLong
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
        job = lifecycleScope.launch(Dispatchers.Default) {
            runCatching { runStream(mp, durationSec) }.onFailure { Log.e(TAG, "live stream ended with error", it) }
            handler.post { stopSelf() }
        }
        return START_NOT_STICKY
    }

    private class Pipeline(val encoder: MediaCodec, val input: Surface, val display: VirtualDisplay, val w: Int, val h: Int) {
        fun release() {
            runCatching { display.release() }
            runCatching { encoder.stop() }
            runCatching { encoder.release() }
            runCatching { input.release() }
        }
    }

    private fun buildPipeline(mp: MediaProjection, size: Pair<Int, Int>): Pipeline {
        val (w, h) = size
        fun format(hints: Boolean) = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, w, h).apply {
            setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
            setInteger(MediaFormat.KEY_BIT_RATE, BITRATE)
            setInteger(MediaFormat.KEY_FRAME_RATE, FPS)
            setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1)
            // A static screen produces no new frames; repeat the last one so the stream never stalls.
            setLong(MediaFormat.KEY_REPEAT_PREVIOUS_FRAME_AFTER, 150_000L)
            setInteger("prepend-sps-pps-to-idr-frames", 1)
            if (hints) {
                setInteger(MediaFormat.KEY_BITRATE_MODE, MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) setInteger(MediaFormat.KEY_PRIORITY, 0)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) setInteger(MediaFormat.KEY_LATENCY, 1)
            }
        }
        var encoder = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
        try {
            encoder.configure(format(true), null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        } catch (e: Exception) {
            // Some encoders reject CBR / latency hints - retry with the bare minimum on a fresh codec.
            runCatching { encoder.release() }
            encoder = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
            encoder.configure(format(false), null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        }
        val input = encoder.createInputSurface()
        encoder.start()
        val display = mp.createVirtualDisplay(
            "mdm-live", w, h, resources.displayMetrics.densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, input, null, handler,
        )
        return Pipeline(encoder, input, display, w, h)
    }

    private suspend fun runStream(mp: MediaProjection, durationSec: Int) = kotlinx.coroutines.coroutineScope {
        val queue = ConcurrentLinkedQueue<ByteArray>()
        val queuedBytes = AtomicLong(0)
        val needKey = java.util.concurrent.atomic.AtomicBoolean(false)
        var pipeline = buildPipeline(mp, targetSize())

        val sender = launch(Dispatchers.IO) {
            val batch = ByteArrayOutputStream(64 * 1024)
            while (isActive) {
                delay(BATCH_MS)
                batch.reset()
                while (true) {
                    val p = queue.poll() ?: break
                    queuedBytes.addAndGet(-p.size.toLong())
                    batch.write(p)
                }
                if (batch.size() == 0) continue
                val ok = runCatching { uploader.upload(batch.toByteArray()) }.getOrDefault(false)
                if (!ok) { // connection hiccup: what was lost is undecodable, so restart from a keyframe
                    needKey.set(true)
                    runCatching { pipeline.encoder.setParameters(Bundle().apply { putInt(MediaCodec.PARAMETER_KEY_REQUEST_SYNC_FRAME, 0) }) }
                }
            }
        }

        val until = System.currentTimeMillis() + durationSec.coerceIn(30, 1800) * 1000L
        val info = MediaCodec.BufferInfo()
        var lastSizeCheck = 0L
        while (isActive && System.currentTimeMillis() < until) {
            val now = System.currentTimeMillis()
            if (now - lastSizeCheck > 1000) { // follow rotation
                lastSizeCheck = now
                val s = targetSize()
                if (s.first != pipeline.w || s.second != pipeline.h) {
                    pipeline.release()
                    pipeline = buildPipeline(mp, s)
                }
            }
            val idx = runCatching { pipeline.encoder.dequeueOutputBuffer(info, 10_000L) }.getOrDefault(-1)
            if (idx < 0) continue
            val buf: ByteBuffer? = pipeline.encoder.getOutputBuffer(idx)
            if (buf != null && info.size > 0) {
                val isConfig = info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0
                val isKey = info.flags and MediaCodec.BUFFER_FLAG_KEY_FRAME != 0
                if (isKey) needKey.set(false)
                if (isConfig || isKey || !needKey.get()) {
                    val payload = ByteArray(info.size)
                    buf.position(info.offset); buf.limit(info.offset + info.size); buf.get(payload)
                    val type = if (isConfig) 1 else if (isKey) 2 else 3
                    val framed = frame(type, info.presentationTimeUs, payload)
                    queue.add(framed)
                    if (queuedBytes.addAndGet(framed.size.toLong()) > MAX_BACKLOG) {
                        // Uplink can't keep up: drop it all and resume at the next keyframe.
                        queue.clear(); queuedBytes.set(0); needKey.set(true)
                        runCatching { pipeline.encoder.setParameters(Bundle().apply { putInt(MediaCodec.PARAMETER_KEY_REQUEST_SYNC_FRAME, 0) }) }
                    }
                }
            }
            runCatching { pipeline.encoder.releaseOutputBuffer(idx, false) }
        }
        sender.cancel()
        pipeline.release()
    }

    private fun frame(type: Int, ptsUs: Long, payload: ByteArray): ByteArray {
        val out = ByteBuffer.allocate(13 + payload.size)
        out.put(type.toByte()).putLong(ptsUs).putInt(payload.size).put(payload)
        return out.array()
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
        private const val FPS = 30
        private const val BITRATE = 4_000_000
        private const val BATCH_MS = 66L
        private const val MAX_BACKLOG = 1_500_000L

        fun intent(context: Context, resultCode: Int, data: Intent, durationSec: Int): Intent =
            Intent(context, LiveScreenService::class.java)
                .putExtra(EXTRA_RESULT_CODE, resultCode)
                .putExtra(EXTRA_DATA, data)
                .putExtra(EXTRA_DURATION, durationSec)
    }
}
