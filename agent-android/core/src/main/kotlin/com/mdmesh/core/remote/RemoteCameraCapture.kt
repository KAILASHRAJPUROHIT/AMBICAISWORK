package com.mdmesh.core.remote

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.ImageFormat
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.media.Image
import android.media.ImageReader
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeoutOrNull
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.resume

/**
 * High-framerate Camera2 capture supporting persistent capture sessions.
 * Keeps CameraDevice and CameraCaptureSession open across successive frames during active
 * live streaming to avoid the 300–800ms hardware re-open penalty on every frame.
 * Automatically releases hardware when idle or explicitly closed.
 */
@Singleton
class RemoteCameraCapture @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private companion object {
        const val TAG = "RemoteCameraCapture"
        const val IDLE_TIMEOUT_MS = 8_000L
        const val FRAME_TIMEOUT_MS = 2_500L
    }

    private val mutex = Mutex()
    private val scope = CoroutineScope(Dispatchers.Default)
    private var activeSession: OpenCameraSession? = null
    private var idleJob: Job? = null

    private class OpenCameraSession(
        val facing: Int,
        val cameraId: String,
        val device: CameraDevice,
        val session: CameraCaptureSession,
        val reader: ImageReader,
        val thread: HandlerThread,
        val handler: Handler,
    ) {
        fun close() {
            runCatching { session.close() }
            runCatching { device.close() }
            runCatching { reader.close() }
            runCatching { thread.quitSafely() }
        }
    }

    /**
     * [facing] one of [CameraCharacteristics.LENS_FACING_FRONT]/[CameraCharacteristics.LENS_FACING_BACK].
     * Returns JPEG bytes, or null if capture failed.
     */
    @SuppressLint("MissingPermission")
    suspend fun captureJpeg(facing: Int): ByteArray? = mutex.withLock {
        idleJob?.cancel()
        idleJob = null

        val current = activeSession
        val session = if (current != null && current.facing == facing) {
            current
        } else {
            activeSession?.close()
            activeSession = null
            openSession(facing)?.also { activeSession = it }
        } ?: return null

        val bytes = withTimeoutOrNull(FRAME_TIMEOUT_MS) {
            takeFrame(session)
        }

        if (bytes == null) {
            Log.w(TAG, "capture timed out or failed for facing=$facing, resetting session")
            activeSession?.close()
            activeSession = null
        } else {
            scheduleIdleClose()
        }

        return bytes
    }

    private suspend fun takeFrame(s: OpenCameraSession): ByteArray? =
        suspendCancellableCoroutine { cont ->
            s.reader.setOnImageAvailableListener({ reader ->
                val image: Image? = runCatching { reader.acquireLatestImage() }.getOrNull()
                val bytes = image?.let {
                    val buffer = it.planes[0].buffer
                    ByteArray(buffer.remaining()).also(buffer::get)
                }
                image?.close()
                if (cont.isActive) cont.resume(bytes)
            }, s.handler)

            runCatching {
                val request = s.device.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE).apply {
                    addTarget(s.reader.surface)
                }.build()
                s.session.capture(request, null, s.handler)
            }.onFailure { err ->
                Log.w(TAG, "session.capture threw for camera ${s.cameraId}", err)
                if (cont.isActive) cont.resume(null)
            }
        }

    @SuppressLint("MissingPermission")
    private suspend fun openSession(facing: Int): OpenCameraSession? {
        val manager = context.getSystemService(Context.CAMERA_SERVICE) as? CameraManager
            ?: run { Log.w(TAG, "no CameraManager"); return null }
        val cameraId = manager.cameraIdList.firstOrNull {
            manager.getCameraCharacteristics(it).get(CameraCharacteristics.LENS_FACING) == facing
        } ?: run { Log.w(TAG, "no camera for facing=$facing"); return null }

        val thread = HandlerThread("RemoteCam-$facing").apply { start() }
        val handler = Handler(thread.looper)

        return suspendCancellableCoroutine { cont ->
            var reader: ImageReader? = null
            var device: CameraDevice? = null

            fun cleanup() {
                runCatching { device?.close() }
                runCatching { reader?.close() }
                thread.quitSafely()
            }

            fun fail(msg: String) {
                Log.w(TAG, msg)
                cleanup()
                if (cont.isActive) cont.resume(null)
            }

            runCatching {
                manager.openCamera(cameraId, object : CameraDevice.StateCallback() {
                    override fun onOpened(cam: CameraDevice) {
                        device = cam
                        val chars = manager.getCameraCharacteristics(cameraId)
                        val sizes = chars.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
                            ?.getOutputSizes(ImageFormat.JPEG)
                        val size = sizes?.minByOrNull { kotlin.math.abs(it.width * it.height - 1280 * 960) }
                            ?: run { fail("no JPEG output sizes for $cameraId"); return }

                        val imgReader = ImageReader.newInstance(size.width, size.height, ImageFormat.JPEG, 2)
                            .also { reader = it }

                        cam.createCaptureSession(
                            listOf(imgReader.surface),
                            object : CameraCaptureSession.StateCallback() {
                                override fun onConfigured(sess: CameraCaptureSession) {
                                    val opened = OpenCameraSession(
                                        facing = facing,
                                        cameraId = cameraId,
                                        device = cam,
                                        session = sess,
                                        reader = imgReader,
                                        thread = thread,
                                        handler = handler,
                                    )
                                    if (cont.isActive) cont.resume(opened)
                                }

                                override fun onConfigureFailed(sess: CameraCaptureSession) {
                                    fail("capture session config failed for $cameraId")
                                }
                            },
                            handler,
                        )
                    }

                    override fun onDisconnected(cam: CameraDevice) {
                        fail("camera $cameraId disconnected")
                    }

                    override fun onError(cam: CameraDevice, error: Int) {
                        fail("camera $cameraId open error=$error")
                    }
                }, handler)
            }.onFailure { err ->
                fail("openCamera threw for $cameraId: ${err.message}")
            }

            cont.invokeOnCancellation { cleanup() }
        }
    }

    private fun scheduleIdleClose() {
        idleJob?.cancel()
        idleJob = scope.launch {
            delay(IDLE_TIMEOUT_MS)
            close()
        }
    }

    /** Explicitly closes any active camera session and releases hardware. */
    fun close() {
        scope.launch {
            mutex.withLock {
                activeSession?.close()
                activeSession = null
            }
        }
    }
}
