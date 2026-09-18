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
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.suspendCancellableCoroutine
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.resume

/** Single-frame JPEG capture via Camera2 — deliberately not a continuous preview/recording
 *  session: opens the camera, takes one photo, closes it, same shape as [RemoteMicCapture]'s
 *  short clips. Requires the CAMERA permission already granted (silently, Device-Owner-only —
 *  see `DeviceOwnerInitializer`); Android's own camera-in-use indicator will show for the
 *  brief moment this runs, same as any app using the camera — there is no way to suppress that
 *  OS-level indicator, by design. */
@Singleton
class RemoteCameraCapture @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    /** [facing] one of [CameraCharacteristics.LENS_FACING_FRONT]/[CameraCharacteristics.LENS_FACING_BACK].
     *  Returns JPEG bytes, or null if no matching camera exists or capture failed. */
    @SuppressLint("MissingPermission") // caller-verified: only invoked when CAMERA is granted
    suspend fun captureJpeg(facing: Int): ByteArray? {
        val manager = context.getSystemService(Context.CAMERA_SERVICE) as? CameraManager ?: return null
        val cameraId = manager.cameraIdList.firstOrNull {
            manager.getCameraCharacteristics(it).get(CameraCharacteristics.LENS_FACING) == facing
        } ?: return null

        val thread = HandlerThread("RemoteCameraCapture").apply { start() }
        val handler = Handler(thread.looper)
        try {
            return suspendCancellableCoroutine { cont ->
                var reader: ImageReader? = null
                var device: CameraDevice? = null
                fun cleanup() {
                    runCatching { device?.close() }
                    runCatching { reader?.close() }
                    thread.quitSafely()
                }
                fun finish(bytes: ByteArray?) {
                    if (cont.isActive) cont.resume(bytes)
                    cleanup()
                }

                runCatching {
                    manager.openCamera(cameraId, object : CameraDevice.StateCallback() {
                        override fun onOpened(cam: CameraDevice) {
                            device = cam
                            val chars = manager.getCameraCharacteristics(cameraId)
                            val sizes = chars.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
                                ?.getOutputSizes(ImageFormat.JPEG)
                            // Cap resolution: this is a periodic monitoring snapshot, not a photo the
                            // admin will print — keep captures small and fast to encode/upload.
                            val size = sizes?.minByOrNull { kotlin.math.abs(it.width * it.height - 1280 * 960) }
                                ?: run { finish(null); return }
                            val imgReader = ImageReader.newInstance(size.width, size.height, ImageFormat.JPEG, 1)
                                .also { reader = it }
                            imgReader.setOnImageAvailableListener({ r ->
                                val image: Image? = r.acquireLatestImage()
                                val bytes = image?.let {
                                    val buffer = it.planes[0].buffer
                                    ByteArray(buffer.remaining()).also(buffer::get)
                                }
                                image?.close()
                                finish(bytes)
                            }, handler)

                            cam.createCaptureSession(
                                listOf(imgReader.surface),
                                object : CameraCaptureSession.StateCallback() {
                                    override fun onConfigured(session: CameraCaptureSession) {
                                        val request = cam.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE).apply {
                                            addTarget(imgReader.surface)
                                        }.build()
                                        runCatching { session.capture(request, null, handler) }
                                            .onFailure { finish(null) }
                                    }
                                    override fun onConfigureFailed(session: CameraCaptureSession) = finish(null)
                                },
                                handler,
                            )
                        }
                        override fun onDisconnected(cam: CameraDevice) = finish(null)
                        override fun onError(cam: CameraDevice, error: Int) = finish(null)
                    }, handler)
                }.onFailure { finish(null) }

                cont.invokeOnCancellation { cleanup() }
            }
        } finally {
            // cleanup() already called from finish() on every path; quitSafely() is idempotent.
            thread.quitSafely()
        }
    }
}
