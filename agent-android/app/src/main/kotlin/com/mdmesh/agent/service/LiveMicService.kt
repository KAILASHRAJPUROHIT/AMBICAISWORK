package com.mdmesh.agent.service

import android.Manifest
import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.SystemClock
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import com.mdmesh.agent.R
import com.mdmesh.core.remote.LiveFrameUploader
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.nio.ByteBuffer
import javax.inject.Inject

/**
 * Live microphone ("listen in"): AudioRecord -> 16-bit mono PCM at 16 kHz -> 80 ms packets -> server relay -> browser
 * (Web Audio). Not a recording: nothing is kept on the tablet or the server, and the stream ends with the session.
 *
 * Packet framing is the live relay's: type(1) | ptsUs(8, BE) | length(4, BE) | payload, with type 1 = config (JSON that
 * names the sample rate) and type 5 = PCM. If the uplink falls behind, the OLDEST audio is dropped so the delay never
 * grows; the listener hears a small gap instead of an ever-later voice.
 *
 * Android shows its own microphone-in-use indicator while this runs. That is by design and cannot be hidden.
 */
@AndroidEntryPoint
class LiveMicService : LifecycleService() {
    @Inject lateinit var uploader: LiveFrameUploader

    private var job: Job? = null

    @SuppressLint("MissingPermission") // checked just below; Device Owner grants RECORD_AUDIO silently
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        val durationSec = intent?.getIntExtra(EXTRA_DURATION, 300) ?: 300
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            Log.w(TAG, "RECORD_AUDIO not granted - live microphone unavailable")
            stopSelf(); return START_NOT_STICKY
        }
        if (!runCatching { startForegroundNow() }.onFailure { Log.e(TAG, "startForeground failed", it) }.isSuccess) {
            stopSelf(); return START_NOT_STICKY
        }
        job?.cancel()
        job = lifecycleScope.launch(kotlinx.coroutines.Dispatchers.IO) {
            runCatching { runStream(durationSec) }
                .onFailure { if (it !is CancellationException) Log.e(TAG, "live microphone ended with error", it) }
            stopSelf()
        }
        return START_NOT_STICKY
    }

    @SuppressLint("MissingPermission")
    private suspend fun runStream(durationSec: Int) = kotlinx.coroutines.coroutineScope {
        val minBuf = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (minBuf <= 0) { Log.e(TAG, "AudioRecord unsupported (min buffer $minBuf)"); return@coroutineScope }
        val record = AudioRecord(
            MediaRecorder.AudioSource.MIC, SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
            maxOf(minBuf, PACKET_BYTES * 4),
        )
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            Log.e(TAG, "AudioRecord failed to initialise (another app may hold the microphone)")
            record.release(); return@coroutineScope
        }
        // Reading never waits on the network: packets go through a small queue that drops the oldest when full.
        val queue = Channel<ByteArray>(capacity = 12, onBufferOverflow = BufferOverflow.DROP_OLDEST)
        val sender = launch {
            uploader.upload(KIND, frame(TYPE_CONFIG, 0L, """{"sr":$SAMPLE_RATE,"ch":1,"fmt":"s16le"}""".toByteArray()))
            for (batch in queue) {
                if (!uploader.upload(KIND, batch)) Log.w(TAG, "audio upload failed")
            }
        }
        try {
            record.startRecording()
            val until = System.currentTimeMillis() + durationSec.coerceIn(30, 1800) * 1000L
            val chunk = ByteArray(PACKET_BYTES)
            while (isActive && System.currentTimeMillis() < until) {
                var filled = 0
                while (filled < PACKET_BYTES && isActive) {
                    val n = record.read(chunk, filled, PACKET_BYTES - filled)
                    if (n <= 0) { Log.w(TAG, "AudioRecord.read returned $n"); return@coroutineScope }
                    filled += n
                }
                val pts = SystemClock.elapsedRealtimeNanos() / 1000
                queue.trySend(frame(TYPE_PCM, pts, chunk.copyOf(filled)))
            }
        } finally {
            runCatching { record.stop() }
            record.release()
            queue.close()
            sender.cancel()
        }
    }

    private fun frame(type: Int, ptsUs: Long, payload: ByteArray): ByteArray {
        val out = ByteBuffer.allocate(13 + payload.size)
        out.put(type.toByte()).putLong(ptsUs).putInt(payload.size).put(payload)
        return out.array()
    }

    private fun startForegroundNow() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && manager.getNotificationChannel(CHANNEL_ID) == null) {
            manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "Remote management", NotificationManager.IMPORTANCE_LOW))
        }
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle("AMBIC MDM live session")
            .setContentText("Live microphone is active")
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    override fun onDestroy() {
        job?.cancel()
        super.onDestroy()
    }

    companion object {
        private const val TAG = "LiveMicService"
        private const val CHANNEL_ID = "mdm_remote_capture"
        private const val NOTIFICATION_ID = 1004
        private const val EXTRA_DURATION = "durationSec"
        private const val KIND = "audio"
        private const val SAMPLE_RATE = 16_000
        /** 80 ms of 16-bit mono. */
        private const val PACKET_BYTES = SAMPLE_RATE * 2 * 80 / 1000
        private const val TYPE_CONFIG = 1
        private const val TYPE_PCM = 5

        fun intent(context: Context, durationSec: Int): Intent =
            Intent(context, LiveMicService::class.java).putExtra(EXTRA_DURATION, durationSec)
    }
}
