package com.aradhana.capturecam

import android.graphics.Rect
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.hardware.camera2.CaptureResult
import android.hardware.camera2.TotalCaptureResult
import android.hardware.camera2.params.MeteringRectangle
import android.util.Log
import androidx.camera.camera2.interop.Camera2CameraControl
import androidx.camera.camera2.interop.Camera2CameraInfo
import androidx.camera.camera2.interop.Camera2Interop
import androidx.camera.camera2.interop.CaptureRequestOptions
import androidx.camera.core.Camera
import androidx.camera.core.Preview
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlin.math.min

/**
 * Wraps CameraX's Camera2 interop layer for continuous jewellery tracking:
 * the app already knows exactly what object matters (the detector's
 * bounding box), so rather than relying on any generic phone-level object
 * tracking (this device's stock camera advertises none beyond face-tracking
 * in video), this drives Camera2's AF/AE region directly at the detected
 * object's center every frame while CONTROL_AF_MODE_CONTINUOUS_PICTURE stays
 * the active mode throughout.
 *
 * Two distinct focus operations, never conflated:
 *  - updateTrackingRegion(): called continuously (every relevant tick) while
 *    hunting/centering/zooming or while the gimbal is moving. Only moves
 *    WHERE continuous AF is looking -- never touches AF_MODE, never issues
 *    CONTROL_AF_TRIGGER. Continuous AF keeps running the whole time.
 *  - triggerAutoFocus(): the one-shot FINAL lock, called ONLY once pose is
 *    settled (gimbal stopped, zoom settled, tracking region stable) and
 *    capture is imminent. This is a real edge-triggered AF sweep
 *    (CONTROL_AF_TRIGGER_START), and per CameraX's own documentation a
 *    triggered/locked AF state does not resume continuous scanning on its
 *    own -- callers must call resumeContinuousTracking() afterward (e.g. on
 *    retake or once the next item is armed) rather than assuming continuous
 *    AF is still active post-capture.
 */
class FocusZoomController {
    private var camera: Camera? = null
    private var camera2Control: Camera2CameraControl? = null
    private var sensorArraySize: Rect? = null

    private val _afState = MutableStateFlow<Int?>(null)
    val afState: StateFlow<Int?> = _afState

    private var lastLoggedPhysicalId: String? = null

    /** Must be called on the Preview.Builder BEFORE binding -- Camera2
     * interop callbacks can only be attached at use-case build time. */
    fun attachCaptureCallback(previewBuilder: Preview.Builder) {
        val extender = Camera2Interop.Extender(previewBuilder)
        extender.setSessionCaptureCallback(object : CameraCaptureSession.CaptureCallback() {
            override fun onCaptureCompleted(
                session: CameraCaptureSession,
                request: CaptureRequest,
                result: TotalCaptureResult
            ) {
                _afState.value = result.get(CaptureResult.CONTROL_AF_STATE)
                // Diagnostic: the logical multi-camera silently switches its
                // ACTIVE physical lens as zoom ratio changes. Logging every
                // transition (not every frame) lets us find exactly which
                // zoom ratio crosses over to the telephoto lens -- that
                // lens's minimum focus distance is 40cm (see CameraDiag
                // physId=3), far past typical jewellery shooting distance,
                // so a crossover mid-shoot would explain a soft/blurred
                // capture with no other symptom.
                val activeId = result.get(CaptureResult.LOGICAL_MULTI_CAMERA_ACTIVE_PHYSICAL_ID)
                if (activeId != null && activeId != lastLoggedPhysicalId) {
                    lastLoggedPhysicalId = activeId
                    val zoom = camera?.cameraInfo?.zoomState?.value?.zoomRatio
                    Log.i("CameraDiag", "active physical camera switched to id=$activeId at zoomRatio=$zoom")
                }
            }
        })
    }

    /** [cameraManager]/[context] are used once at bind time to read the
     * active sensor array size (needed to convert normalized 0..1 detector
     * coordinates into Camera2's pixel-space MeteringRectangle) -- fails
     * open (region tracking silently no-ops) if characteristics can't be
     * read rather than crashing the bind. */
    fun bind(camera: Camera, cameraManager: CameraManager) {
        this.camera = camera
        this.camera2Control = Camera2CameraControl.from(camera.cameraControl)
        try {
            val cameraId = Camera2CameraInfo.from(camera.cameraInfo).cameraId
            sensorArraySize = cameraManager.getCameraCharacteristics(cameraId)
                .get(CameraCharacteristics.SENSOR_INFO_ACTIVE_ARRAY_SIZE)
        } catch (e: Exception) {
            Log.w("CameraDiag", "Could not read sensor array size -- tracking region updates will no-op", e)
            sensorArraySize = null
        }
    }

    /** Enables continuous-picture AF as the persistent baseline (NOT a
     * one-shot trigger) -- call once when tracking begins for an item, and
     * again after every triggerAutoFocus() lock is done with (retake, next
     * item), since a trigger/lock does not resume scanning on its own. */
    fun startContinuousTracking() {
        val control = camera2Control ?: return
        val options = CaptureRequestOptions.Builder()
            .setCaptureRequestOption(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE)
            .setCaptureRequestOption(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON)
            .build()
        control.setCaptureRequestOptions(options)
    }

    /** Moves the AF/AE metering region to follow the detected jewellery
     * center -- WITHOUT touching AF_MODE and WITHOUT triggering, so
     * continuous AF keeps running uninterrupted, just now aimed at wherever
     * the detector says the object is. [cx]/[cy] are normalized (0..1)
     * upright-frame coordinates, same space bestObjectBox()/MaterialDetector
     * bounds already use. Safe to call every tick, including while the
     * gimbal is mid-move (RSC2Controller.isMoving) -- that's the whole
     * point: tracking continues through motion, capture just doesn't. */
    fun updateTrackingRegion(cx: Float, cy: Float) {
        val control = camera2Control ?: return
        val array = sensorArraySize ?: return
        val regionSize = (min(array.width(), array.height()) * 0.2f).toInt().coerceAtLeast(1)
        val px = (cx * array.width()).toInt().coerceIn(regionSize / 2, array.width() - regionSize / 2)
        val py = (cy * array.height()).toInt().coerceIn(regionSize / 2, array.height() - regionSize / 2)
        val rect = Rect(px - regionSize / 2, py - regionSize / 2, px + regionSize / 2, py + regionSize / 2)
        val region = arrayOf(MeteringRectangle(rect, MeteringRectangle.METERING_WEIGHT_MAX))
        val options = CaptureRequestOptions.Builder()
            .setCaptureRequestOption(CaptureRequest.CONTROL_AF_REGIONS, region)
            .setCaptureRequestOption(CaptureRequest.CONTROL_AE_REGIONS, region)
            .build()
        control.setCaptureRequestOptions(options)
    }

    /** The final one-shot focus lock -- call ONLY once pose/zoom/tracking
     * are all settled and capture is about to happen. CONTROL_AF_TRIGGER_START
     * is edge-triggered, always forces a fresh search regardless of what
     * AF_MODE was already active. Per CameraX's own docs, a triggered lock
     * does not resume continuous scanning by itself afterward -- call
     * startContinuousTracking() again once done with this item (retake,
     * next item) rather than assuming tracking is still live. */
    fun triggerAutoFocus() {
        val control = camera2Control ?: return
        _afState.value = null
        val options = CaptureRequestOptions.Builder()
            .setCaptureRequestOption(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_AUTO)
            .setCaptureRequestOption(CaptureRequest.CONTROL_AF_TRIGGER, CaptureRequest.CONTROL_AF_TRIGGER_START)
            .build()
        control.setCaptureRequestOptions(options)
    }

    /** Definitive post-trigger lock state -- only meaningful right after
     * triggerAutoFocus(), the final gate before actually shuttering. */
    fun isFocusLocked(state: Int?): Boolean =
        state == CaptureResult.CONTROL_AF_STATE_FOCUSED_LOCKED

    fun isFocusFailed(state: Int?): Boolean =
        state == CaptureResult.CONTROL_AF_STATE_NOT_FOCUSED_LOCKED

    /** Good-enough-to-keep-working state DURING continuous tracking
     * (hunting/centering/zoom-climb) -- CONTROL_AF_MODE_CONTINUOUS_PICTURE
     * never reports FOCUSED_LOCKED (that's a triggered-mode-only state), it
     * reports PASSIVE_FOCUSED/PASSIVE_SCAN instead. Used to gate zoom
     * climbing on "focus looks reasonable right now", NOT as the final
     * capture confirmation -- that's still triggerAutoFocus()+isFocusLocked(). */
    fun isTrackingFocused(state: Int?): Boolean =
        state == CaptureResult.CONTROL_AF_STATE_PASSIVE_FOCUSED

    fun zoomRatioRange(): ClosedFloatingPointRange<Float> {
        val state = camera?.cameraInfo?.zoomState?.value
        val min = state?.minZoomRatio ?: 1f
        val max = state?.maxZoomRatio ?: 1f
        return min..max
    }

    fun currentZoomRatio(): Float = camera?.cameraInfo?.zoomState?.value?.zoomRatio ?: 1f

    fun setZoomRatio(ratio: Float) {
        val range = zoomRatioRange()
        camera?.cameraControl?.setZoomRatio(ratio.coerceIn(range.start, range.endInclusive))
    }
}
