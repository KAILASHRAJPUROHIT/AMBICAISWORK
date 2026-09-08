package com.aradhana.capturecam

import android.graphics.Rect
import android.os.Handler
import android.os.Looper
import android.os.Build
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
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
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
@androidx.annotation.OptIn(markerClass = [ExperimentalCamera2Interop::class])
class FocusZoomController {
    private var camera: Camera? = null
    private var camera2Control: Camera2CameraControl? = null
    private var sensorArraySize: Rect? = null
    private var exposureCompensationRange: android.util.Range<Int>? = null
    private var exposureCompensationStepEv: Float = 0f

    private val _afState = MutableStateFlow<Int?>(null)
    val afState: StateFlow<Int?> = _afState

    private var lastLoggedPhysicalId: String? = null

    // ---- Consolidated Camera2 interop option state ----
    // CRITICAL: Camera2CameraControl.setCaptureRequestOptions() REPLACES
    // the entire persistent option set on every call -- it does not merge
    // with whatever a previous call set. Confirmed the hard way
    // (2026-08-18): updateTrackingRegion()'s AE_REGIONS and
    // triggerAutoFocus()'s AF_TRIGGER were each built from their own
    // isolated CaptureRequestOptions.Builder, silently wiping out
    // whatever the OTHER call had most recently set (region tracking
    // clobbering a pending AF trigger was the specific bug that shipped;
    // AE_REGIONS getting dropped by every triggerAutoFocus() call was a
    // second, latent instance of the same root cause). Every field this
    // controller wants to keep persistent now lives here, and every
    // setter updates its own field(s) then calls applyOptions(), which
    // rebuilds and sends the FULL set in one call -- so no setter can
    // ever silently erase another's state again.
    private var afMode: Int? = null
    private var aeMode: Int? = null
    private var afTrigger: Int? = null
    private var afRegions: Array<MeteringRectangle>? = null
    private var aeRegions: Array<MeteringRectangle>? = null
    private var exposureCompensation: Int? = null

    private fun applyOptions() {
        val control = camera2Control ?: return
        val builder = CaptureRequestOptions.Builder()
        afMode?.let { builder.setCaptureRequestOption(CaptureRequest.CONTROL_AF_MODE, it) }
        aeMode?.let { builder.setCaptureRequestOption(CaptureRequest.CONTROL_AE_MODE, it) }
        afTrigger?.let { builder.setCaptureRequestOption(CaptureRequest.CONTROL_AF_TRIGGER, it) }
        afRegions?.let { builder.setCaptureRequestOption(CaptureRequest.CONTROL_AF_REGIONS, it) }
        aeRegions?.let { builder.setCaptureRequestOption(CaptureRequest.CONTROL_AE_REGIONS, it) }
        exposureCompensation?.let { builder.setCaptureRequestOption(CaptureRequest.CONTROL_AE_EXPOSURE_COMPENSATION, it) }
        control.setCaptureRequestOptions(builder.build())
    }

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
                val activeId = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    result.get(CaptureResult.LOGICAL_MULTI_CAMERA_ACTIVE_PHYSICAL_ID)
                } else null
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
            val characteristics = cameraManager.getCameraCharacteristics(cameraId)
            sensorArraySize = characteristics.get(CameraCharacteristics.SENSOR_INFO_ACTIVE_ARRAY_SIZE)
            exposureCompensationRange = characteristics.get(CameraCharacteristics.CONTROL_AE_COMPENSATION_RANGE)
            exposureCompensationStepEv = characteristics.get(CameraCharacteristics.CONTROL_AE_COMPENSATION_STEP)
                ?.let { it.numerator.toFloat() / it.denominator } ?: 0f
            Log.d("CameraDiag", "exposure compensation range=$exposureCompensationRange stepEv=$exposureCompensationStepEv")
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
        afMode = CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE
        aeMode = CaptureRequest.CONTROL_AE_MODE_ON
        afTrigger = null
        applyOptions()
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
        val array = sensorArraySize ?: return
        if (camera2Control == null) return
        val regionSize = (min(array.width(), array.height()) * 0.2f).toInt().coerceAtLeast(1)
        val px = (cx * array.width()).toInt().coerceIn(regionSize / 2, array.width() - regionSize / 2)
        val py = (cy * array.height()).toInt().coerceIn(regionSize / 2, array.height() - regionSize / 2)
        val rect = Rect(px - regionSize / 2, py - regionSize / 2, px + regionSize / 2, py + regionSize / 2)
        val region = arrayOf(MeteringRectangle(rect, MeteringRectangle.METERING_WEIGHT_MAX))
        afRegions = region
        aeRegions = region
        applyOptions()
    }

    /** The final one-shot focus lock -- call ONLY once pose/zoom/tracking
     * are all settled and capture is about to happen. CONTROL_AF_TRIGGER_START
     * is edge-triggered, always forces a fresh search regardless of what
     * AF_MODE was already active. Per CameraX's own docs, a triggered lock
     * does not resume continuous scanning by itself afterward -- call
     * startContinuousTracking() again once done with this item (retake,
     * next item) rather than assuming tracking is still live. */
    fun triggerAutoFocus() {
        if (camera2Control == null) return
        _afState.value = null
        afMode = CaptureRequest.CONTROL_AF_MODE_AUTO
        afTrigger = CaptureRequest.CONTROL_AF_TRIGGER_START
        applyOptions()
        // CRITICAL: Camera2CameraControl.setCaptureRequestOptions() is a
        // PERSISTENT modifier applied to every REPEATING capture request
        // from here on, not a single one-shot frame -- unlike a raw
        // CameraCaptureSession where you'd send one capture() with the
        // trigger then let the repeating request resume untouched.
        // CONTROL_AF_TRIGGER_START is supposed to be an edge (one request
        // only); leaving it set on every repeating request instead keeps
        // re-triggering a fresh AF sweep every single frame, so Camera2
        // never gets a chance to settle into FOCUSED_LOCKED -- it just
        // restarts forever. Root-caused live (2026-08-18): af state sat on
        // "active-scan" for 60+ seconds straight on an already-sharp,
        // stationary, well-lit subject, which is not a real AF search
        // duration for that scenario. Clearing the trigger back to IDLE
        // shortly after (AF_MODE stays AUTO so the search that's already
        // in flight isn't cancelled) lets the one sweep actually complete
        // and report a definitive LOCKED/NOT_FOCUSED_LOCKED result instead
        // of being restarted every ~150ms tick.
        Handler(Looper.getMainLooper()).postDelayed({
            if (camera2Control == null) return@postDelayed
            afTrigger = CaptureRequest.CONTROL_AF_TRIGGER_IDLE
            applyOptions()
        }, 200L)
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

    // ---- Exposure control (2026-08-18) ----
    // Per explicit request: automated exposure control so gold reads
    // correctly and specular reflections don't blow out fine design
    // detail (engraving, facets, stone settings) -- the recurring root
    // cause behind several bugs chased earlier this session (a display
    // box's glare, blown-out ring facets confusing the colour detector).
    // This only ever biases the camera's OWN metered exposure
    // (CONTROL_AE_EXPOSURE_COMPENSATION), it does not switch to full
    // manual exposure (CONTROL_AE_MODE_OFF) -- staying in AE_MODE_ON with
    // a bias keeps the camera's own metering doing the heavy lifting
    // (still correct for ordinary lighting changes), the bias just nudges
    // it toward protecting highlights when gold specifically is
    // clipping. See MainActivity's applyAutoExposure() for the actual
    // decision logic (reads MaterialDetector.Result.highlightClipFraction).

    /** True once bind() has successfully read the device's real
     * compensation range/step -- callers should not attempt exposure
     * control before this (there's nothing to clamp against). */
    fun exposureControlAvailable(): Boolean = exposureCompensationRange != null

    /** Exposure compensation range in whole EV stops (not raw device
     * steps), for callers reasoning about "how far can I push this." */
    fun exposureCompensationRangeEv(): ClosedFloatingPointRange<Float> {
        val range = exposureCompensationRange ?: return 0f..0f
        val step = exposureCompensationStepEv.takeIf { it > 0f } ?: 1f
        return (range.lower * step)..(range.upper * step)
    }

    /** Sets exposure bias in EV stops (e.g. -1.0f = one stop darker),
     * clamped to the device's real supported range and quantized to its
     * real step size -- an unclamped/unquantized value is silently
     * rejected by Camera2 on some devices, which would look like this
     * function doing nothing. Safe to call every tick; only actually
     * issues a new capture request when the quantized step value
     * changes, so it doesn't spam applyOptions() when the target hasn't
     * moved. */
    fun setExposureCompensationEv(ev: Float) {
        val range = exposureCompensationRange ?: return
        val step = exposureCompensationStepEv.takeIf { it > 0f } ?: return
        val steps = Math.round(ev / step).coerceIn(range.lower, range.upper)
        if (exposureCompensation == steps) return
        exposureCompensation = steps
        applyOptions()
    }
}
