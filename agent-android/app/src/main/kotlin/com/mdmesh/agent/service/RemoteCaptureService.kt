package com.mdmesh.agent.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.camera2.CameraCharacteristics
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import com.mdmesh.agent.R
import com.mdmesh.core.remote.RemoteCameraCapture
import com.mdmesh.core.remote.RemoteMicCapture
import com.mdmesh.core.remote.RemoteSnapshotUploader
import com.mdmesh.core.remote.ScreenCaptureAccessibilityService
import com.mdmesh.proto.RemoteSessionStartPayload
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Foreground, bounded periodic snapshot service. It never retains capture history locally. */
@AndroidEntryPoint
class RemoteCaptureService : LifecycleService() {
    @Inject lateinit var uploader: RemoteSnapshotUploader
    @Inject lateinit var camera: RemoteCameraCapture
    @Inject lateinit var mic: RemoteMicCapture

    private var captureJob: Job? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val session = intent?.toSession() ?: return Service.START_NOT_STICKY
        val started = runCatching { startForegroundFor(session) }
            .onFailure { Log.e(TAG, "startForeground failed for session ${session.sessionId}", it) }
            .isSuccess
        if (!started) return Service.START_NOT_STICKY
        captureJob?.cancel()
        captureJob = lifecycleScope.launch {
            val until = System.currentTimeMillis() + session.durationSec.coerceIn(30, 1800) * 1000L
            val interval = session.intervalSec.coerceIn(1, 60) * 1000L
            while (System.currentTimeMillis() < until) {
                session.kinds.forEach { kind ->
                    runCatching { captureAndUpload(kind) }
                        .onFailure { Log.w(TAG, "capture/upload threw for kind=$kind", it) }
                }
                delay(interval)
            }
            stopSelf(startId)
        }
        return Service.START_NOT_STICKY
    }

    private suspend fun captureAndUpload(kind: String) {
        val capture = when (kind) {
            "screen" -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                ScreenCaptureAccessibilityService.captureJpeg()?.let { "image/jpeg" to it }
            } else null
            "cameraFront" -> camera.captureJpeg(CameraCharacteristics.LENS_FACING_FRONT)?.let { "image/jpeg" to it }
            "cameraBack" -> camera.captureJpeg(CameraCharacteristics.LENS_FACING_BACK)?.let { "image/jpeg" to it }
            "mic" -> mic.captureAac()?.let { "audio/mp4" to it }
            else -> null
        }
        if (capture == null) {
            Log.w(TAG, "capture returned null for kind=$kind")
            return
        }
        val uploaded = uploader.upload(kind, capture.first, capture.second)
        if (!uploaded) Log.w(TAG, "upload failed for kind=$kind (${capture.second.size} bytes)")
    }

    override fun onDestroy() {
        captureJob?.cancel()
        super.onDestroy()
    }

    private fun startForegroundFor(session: RemoteSessionStartPayload) {
        ensureChannel()
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle("AMBIC MDM remote session")
            .setContentText("A time-limited management capture session is active")
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            var type = ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            if ("cameraFront" in session.kinds || "cameraBack" in session.kinds) type = type or ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA
            if ("mic" in session.kinds) type = type or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
            startForeground(NOTIFICATION_ID, notification, type)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (manager.getNotificationChannel(CHANNEL_ID) == null) {
            manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "Remote management", NotificationManager.IMPORTANCE_LOW))
        }
    }

    private fun Intent.toSession(): RemoteSessionStartPayload? {
        val sessionId = getStringExtra(EXTRA_SESSION_ID) ?: return null
        return RemoteSessionStartPayload(
            sessionId = sessionId,
            durationSec = getIntExtra(EXTRA_DURATION, 300),
            intervalSec = getIntExtra(EXTRA_INTERVAL, 3),
            kinds = getStringArrayListExtra(EXTRA_KINDS)?.toList() ?: emptyList(),
        )
    }

    companion object {
        private const val TAG = "RemoteCaptureService"
        private const val CHANNEL_ID = "mdm_remote_capture"
        private const val NOTIFICATION_ID = 1002
        private const val EXTRA_SESSION_ID = "sessionId"
        private const val EXTRA_DURATION = "durationSec"
        private const val EXTRA_INTERVAL = "intervalSec"
        private const val EXTRA_KINDS = "kinds"

        fun intent(context: Context, payload: RemoteSessionStartPayload): Intent =
            Intent(context, RemoteCaptureService::class.java).apply {
                putExtra(EXTRA_SESSION_ID, payload.sessionId)
                putExtra(EXTRA_DURATION, payload.durationSec)
                putExtra(EXTRA_INTERVAL, payload.intervalSec)
                putStringArrayListExtra(EXTRA_KINDS, ArrayList(payload.kinds))
            }
    }
}

/** :app implementation of the :core command bridge. */
class AgentRemoteCaptureController(private val context: Context) : com.mdmesh.core.remote.RemoteCaptureController {
    override fun start(payload: RemoteSessionStartPayload): Boolean = runCatching {
        ContextCompat.startForegroundService(context, RemoteCaptureService.intent(context, payload))
        true
    }.getOrDefault(false)

    override fun stop() {
        context.stopService(Intent(context, RemoteCaptureService::class.java))
    }
}
