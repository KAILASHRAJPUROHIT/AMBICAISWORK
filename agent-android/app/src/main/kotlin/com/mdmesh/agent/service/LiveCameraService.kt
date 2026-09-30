package com.mdmesh.agent.service

import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.media.MediaCodec
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import android.util.Range
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
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import javax.inject.Inject
import kotlin.coroutines.resume

/**
 * Live front or back camera: Camera2 -> hardware H.264 encoder -> server relay, same wire format as
 * the screen stream ([LiveEncoderPump]). Asks the camera for the highest frame rate it offers up to
 * 60 fps at ~720p; tablet cameras that top out at 30 fps stream at 30. A meta packet tells the
 * browser how to rotate/mirror the sensor image upright.
 */
@AndroidEntryPoint
class LiveCameraService : LifecycleService() {
    @Inject lateinit var uploader: LiveFrameUploader

    private val jobs = java.util.concurrent.ConcurrentHashMap<Boolean, Job>() // front? -> stream; front and back can run together

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        val front = intent?.getBooleanExtra(EXTRA_FRONT, true) ?: true
        val durationSec = intent?.getIntExtra(EXTRA_DURATION, 300) ?: 300
        if (!runCatching { startForegroundNow() }.onFailure { Log.e(TAG, "startForeground failed", it) }.isSuccess) {
            stopSelf(); return START_NOT_STICKY
        }
        jobs[front]?.cancel()
        jobs[front] = lifecycleScope.launch(Dispatchers.Default) {
            runCatching { runCamera(front, durationSec) }.onFailure { Log.e(TAG, "camera stream ended with error", it) }
            jobs.remove(front)
            if (jobs.isEmpty()) stopSelf()
        }
        return START_NOT_STICKY
    }

    @SuppressLint("MissingPermission")
    private suspend fun runCamera(front: Boolean, durationSec: Int) = kotlinx.coroutines.coroutineScope {
        val cm = getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val wanted = if (front) CameraCharacteristics.LENS_FACING_FRONT else CameraCharacteristics.LENS_FACING_BACK
        val id = cm.cameraIdList.firstOrNull { cm.getCameraCharacteristics(it).get(CameraCharacteristics.LENS_FACING) == wanted }
            ?: return@coroutineScope
        val chars = cm.getCameraCharacteristics(id)
        val sensor = chars.get(CameraCharacteristics.SENSOR_ORIENTATION) ?: 0

        val map = chars.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP) ?: return@coroutineScope
        val sizes = map.getOutputSizes(MediaCodec::class.java) ?: return@coroutineScope
        // Prefer 1280x720; otherwise the largest size not above 1280 wide.
        val size = sizes.firstOrNull { it.width == 1280 && it.height == 720 }
            ?: sizes.filter { it.width <= 1280 }.maxByOrNull { it.width * it.height }
            ?: sizes.minByOrNull { it.width * it.height }!!
        val ranges = chars.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES) ?: emptyArray()
        val range: Range<Int> = ranges.filter { it.upper <= 60 }.maxWithOrNull(compareBy({ it.upper }, { it.lower }))
            ?: Range(15, 30)
        val fps = range.upper.coerceIn(15, 60)

        val kind = if (front) "cameraFront" else "cameraBack"
        val pump = LiveEncoderPump(kind, uploader, fps, if (fps > 30) 8_000_000 else 5_000_000)
        pump.startSender(this)
        val surface: Surface = pump.open(size.width, size.height)

        val ht = HandlerThread("mdm-live-cam-$kind").also { it.start() }
        val handler = Handler(ht.looper)

        val camera: CameraDevice = suspendCancellableCoroutine { cont ->
            cm.openCamera(id, object : CameraDevice.StateCallback() {
                override fun onOpened(device: CameraDevice) { if (cont.isActive) cont.resume(device) else device.close() }
                override fun onDisconnected(device: CameraDevice) { device.close() }
                override fun onError(device: CameraDevice, error: Int) { device.close(); if (cont.isActive) cont.cancel() }
            }, handler)
        }
        val session: CameraCaptureSession = suspendCancellableCoroutine { cont ->
            @Suppress("DEPRECATION")
            camera.createCaptureSession(listOf(surface), object : CameraCaptureSession.StateCallback() {
                override fun onConfigured(s: CameraCaptureSession) { if (cont.isActive) cont.resume(s) }
                override fun onConfigureFailed(s: CameraCaptureSession) { if (cont.isActive) cont.cancel() }
            }, handler)
        }
        val request = camera.createCaptureRequest(CameraDevice.TEMPLATE_RECORD).apply {
            addTarget(surface)
            set(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, range)
        }.build()
        session.setRepeatingRequest(request, null, handler)

        var lastMeta = -1
        val until = System.currentTimeMillis() + durationSec.coerceIn(30, 1800) * 1000L
        try {
            while (isActive && System.currentTimeMillis() < until) {
                val disp = displayRotation()
                if (disp != lastMeta) { // upright the picture for the way the tablet is held right now
                    lastMeta = disp
                    val rotation = if (front) (sensor + disp) % 360 else (sensor - disp + 360) % 360
                    pump.meta("""{"rotation":$rotation,"mirror":$front,"fps":$fps}""")
                }
                pump.drainOnce()
            }
        } finally {
            runCatching { session.close() }
            runCatching { camera.close() }
            pump.stop()
            ht.quitSafely()
        }
    }

    @Suppress("DEPRECATION")
    private fun displayRotation(): Int = when ((getSystemService(Context.WINDOW_SERVICE) as WindowManager).defaultDisplay.rotation) {
        Surface.ROTATION_90 -> 90
        Surface.ROTATION_180 -> 180
        Surface.ROTATION_270 -> 270
        else -> 0
    }

    private fun startForegroundNow() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && manager.getNotificationChannel(CHANNEL_ID) == null) {
            manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "Remote management", NotificationManager.IMPORTANCE_LOW))
        }
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle("AMBIC MDM live session")
            .setContentText("Live camera is active")
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    override fun onDestroy() {
        jobs.values.forEach { it.cancel() }
        super.onDestroy()
    }

    companion object {
        private const val TAG = "LiveCameraService"
        private const val CHANNEL_ID = "mdm_remote_capture"
        private const val NOTIFICATION_ID = 1010
        private const val EXTRA_FRONT = "front"
        private const val EXTRA_DURATION = "durationSec"

        fun intent(context: Context, front: Boolean, durationSec: Int): Intent =
            Intent(context, LiveCameraService::class.java)
                .putExtra(EXTRA_FRONT, front)
                .putExtra(EXTRA_DURATION, durationSec)
    }
}

