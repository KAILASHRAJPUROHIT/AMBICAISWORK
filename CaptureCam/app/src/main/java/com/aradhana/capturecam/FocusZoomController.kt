package com.aradhana.capturecam

import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CaptureRequest
import android.hardware.camera2.CaptureResult
import android.hardware.camera2.TotalCaptureResult
import androidx.camera.camera2.interop.Camera2CameraControl
import androidx.camera.camera2.interop.Camera2Interop
import androidx.camera.camera2.interop.CaptureRequestOptions
import androidx.camera.core.Camera
import androidx.camera.core.Preview
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Wraps CameraX's Camera2 interop layer for the two things the web version
 * of this tool could never actually get from a browser: a REAL forced
 * autofocus trigger (CONTROL_AF_TRIGGER_START -- distinct from just
 * reapplying a focus-mode constraint and hoping the platform notices a
 * change) and REAL autofocus state feedback (CONTROL_AF_STATE straight
 * from the camera HAL, not inferred after the fact from a blur-variance
 * heuristic on a downscaled preview frame). See capture.html's
 * _lockFocusOnce/advanceCapturePipeline for the web-side workarounds this
 * replaces.
 */
class FocusZoomController {
    private var camera: Camera? = null
    private var camera2Control: Camera2CameraControl? = null

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
                    android.util.Log.i("CameraDiag", "active physical camera switched to id=$activeId at zoomRatio=$zoom")
                }
            }
        })
    }

    fun bind(camera: Camera) {
        this.camera = camera
        this.camera2Control = Camera2CameraControl.from(camera.cameraControl)
    }

    /** Real AF sweep, not a same-value-no-op risk: CONTROL_AF_TRIGGER_START
     * is an edge-triggered command, always forces a fresh search regardless
     * of what AF_MODE was already active. */
    fun triggerAutoFocus() {
        val control = camera2Control ?: return
        _afState.value = null
        val options = CaptureRequestOptions.Builder()
            .setCaptureRequestOption(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_AUTO)
            .setCaptureRequestOption(CaptureRequest.CONTROL_AF_TRIGGER, CaptureRequest.CONTROL_AF_TRIGGER_START)
            .build()
        control.setCaptureRequestOptions(options)
    }

    fun isFocusLocked(state: Int?): Boolean =
        state == CaptureResult.CONTROL_AF_STATE_FOCUSED_LOCKED

    fun isFocusFailed(state: Int?): Boolean =
        state == CaptureResult.CONTROL_AF_STATE_NOT_FOCUSED_LOCKED

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
