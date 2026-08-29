package com.aradhana.capturecam

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.hardware.camera2.CaptureResult
import android.os.SystemClock
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.SeekBar
import android.widget.Spinner
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.aradhana.capturecam.databinding.ActivityMainBinding
import com.aradhana.capturecam.databinding.DialogSettingsBinding
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.objects.ObjectDetection
import com.google.mlkit.vision.objects.defaults.ObjectDetectorOptions
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.opencv.core.Mat
import java.io.File
import java.nio.ByteBuffer
import java.util.Arrays
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Smart-camera companion for JewelleryCatalogTool's browser-based capture
 * tool (templates/capture.html). Does ONLY the hard part -- auto-zoom,
 * real-AF-state autofocus, and auto-capture for the jewel + tag shots --
 * then uploads straight to capture_server.py's existing /api/capture/save.
 * Tray management, dedup review, undo, etc. all stay in the web tool
 * exactly as they work today; this app doesn't touch any of that.
 *
 * See capture.html's advanceCapturePipeline for the browser-side state
 * machine this mirrors -- same overall shape (verify at the current zoom
 * before ever advancing, never judge sharpness on a too-small crop, one
 * absolute stall safety valve) but driven by Camera2's real
 * CONTROL_AF_STATE instead of a blur-variance heuristic on a downscaled
 * frame, which is the actual advantage of being native at all.
 */
@androidx.annotation.OptIn(
    markerClass = [ExperimentalGetImage::class, ExperimentalCamera2Interop::class]
)
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var cameraProvider: ProcessCameraProvider
    private val focusZoom = FocusZoomController()
    private var imageCapture: ImageCapture? = null
    private var camera: Camera? = null
    private enum class ProductionCameraSource { PHONE, SONY }
    private enum class RequestedCameraMode { DSLR, SMARTPHONE }
    @Volatile private var activeCameraSource = ProductionCameraSource.SONY
    private lateinit var sonyProduction: SonyProductionCamera
    private var appliedCameraMode: RequestedCameraMode? = null
    @Volatile private var cameraModeEpoch = 0L
    private var cameraProviderRequestInFlight = false
    private var cameraPermissionRequestInFlight = false
    private var cameraPermissionRequestedThisSession = false
    @Volatile private var sonyZoomRatio = 1f
    @Volatile private var sonyZoomTarget = 1f
    private var sonyManualZoomPendingSteps = 0
    private var sonyManualZoomInFlight = false
    private var sonyManualZoomBusyRetries = 0
    @Volatile private var sonyAfRequestedAt = 0L
    @Volatile private var sonyAfRequestedAtNanos = 0L
    @Volatile private var sonyAfCommandAcknowledged = false
    @Volatile private var sonyFocusX = 0.5f
    @Volatile private var sonyFocusY = 0.5f
    private var sonyQualityApplyScheduled = false
    // Throttles rebindUseCases-on-capture-failure so a genuinely dead
    // session gets one recovery attempt per cooldown window instead of a
    // rebind storm if failures keep coming.
    private var lastCameraRebindAt = 0L
    // RSC 2 3-angle workflow -- fails open to the existing single-image
    // flow when no gimbal is connected (spec rule 61: single-image mode
    // must not break just because the gimbal/calibration layer isn't
    // available). Fixed test deflections until real per-category
    // calibration profiles are wired in; axis3 avoided since its effect
    // isn't confirmed (see RSC2Controller's doc comment).
    private val rsc2 = RSC2Controller()

    // ---- DINO(laptop)+MIL(phone) tracking pipeline -----------------------
    // VisionServoController is the single control authority for this
    // pipeline's state and servo decisions; MainActivity only feeds it
    // camera frames + DINO results and executes the ServoCommand it
    // returns via applyServoCommand() -- see that function's doc comment
    // for why it's the ONLY place issuing rsc2/zoom calls for this path.
    private val visionServo = VisionServoController { msg -> Log.i("VisionServo", msg) }
    private var detectorClient: DetectorClient? = null
    private var lastDetectorSendAt = 0L
    private var cachedRotationDegrees = 0
    private var lastServoAt = 0L
    private var lastServoAxisWasPan = true
    private var lastZoomServoAt = 0L

    // Debug-only hook so an axis can be tested live via ADB while someone
    // watches the gimbal, without needing to operate the diagnostics
    // screen's UI by hand: adb shell am broadcast -a
    // com.aradhana.capturecam.TEST_MOVE --ei axis1 1024 --ei axis2 1024
    // --ei axis3 1300 --el durationMs 900. Any axis omitted defaults to
    // center. Moves out, holds briefly, then returns home automatically.
    private val testMoveReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val a1 = intent.getIntExtra("axis1", DumlProtocol.AXIS_CENTER)
            val a2 = intent.getIntExtra("axis2", DumlProtocol.AXIS_CENTER)
            val a3 = intent.getIntExtra("axis3", DumlProtocol.AXIS_CENTER)
            val duration = intent.getLongExtra("durationMs", 900L)
            Log.i(TAG, "testMoveReceiver: axis=($a1,$a2,$a3) duration=$duration rsc2.isReady=${rsc2.isReady}")
            rsc2.moveOut(a1, a2, a3, durationMs = duration) {
                Log.i(TAG, "testMoveReceiver: arrived, holding 2s then returning")
                handler.postDelayed({
                    rsc2.returnHome(a1, a2, a3, durationMs = duration) {
                        Log.i(TAG, "testMoveReceiver: returned home")
                    }
                }, 2000L)
            }
        }
    }
    // Debug-only hook mirroring testMoveReceiver, for proving exposure
    // compensation actually reaches the camera before trusting the AUTO
    // algorithm's tuning: adb shell am broadcast -a
    // com.aradhana.capturecam.TEST_EXPOSURE --ef ev -2.0
    // Sets exposure compensation directly and leaves it there (no auto-
    // revert) so a before/after screenshot shows the real effect. Also
    // disarms auto-exposure's own EV bookkeeping (autoExposureEv) so the
    // next applyAutoExposure() tick doesn't immediately overwrite this
    // with its own (possibly 0) value.
    private val testExposureReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val ev = intent.getFloatExtra("ev", 0f)
            manualExposureOverride = true
            autoExposureEv = ev
            setCameraExposureCompensationEv(ev)
            Log.i(TAG, "testExposureReceiver: set ev=$ev available=${cameraExposureControlAvailable()} range=${cameraExposureRangeEv()}")
        }
    }
    // Deterministic hardware-test hook; avoids coordinate-based UI taps
    // being mistaken for tap-to-focus on a continuously updating preview.
    // adb shell am broadcast -a com.aradhana.capturecam.TEST_ZOOM --ef ratio 1.75
    private val testZoomReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val ratio = intent.getFloatExtra("ratio", 1f)
                .coerceIn(SONY_MIN_ZOOM_RATIO, SONY_MAX_ZOOM_RATIO)
            setCameraZoomRatio(ratio)
            Log.i(TAG, "testZoomReceiver: requested ratio=$ratio source=$activeCameraSource")
        }
    }
    // Raw power-zoom motor verification. Direction is "tele" or "wide".
    // adb shell am broadcast -a com.aradhana.capturecam.TEST_ZOOM_MOTOR
    // --es direction wide --el durationMs 600
    private val testZoomMotorReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val tele = intent.getStringExtra("direction")?.lowercase() != "wide"
            val durationMs = intent.getLongExtra("durationMs", 600L).coerceIn(80L, 1_800L)
            sonyProduction.driveZoom(tele, durationMs) { ok ->
                Log.i(TAG, "testZoomMotorReceiver: tele=$tele durationMs=$durationMs ok=$ok")
            }
        }
    }
    // Deterministic remote touch-focus test in normalized Live View space.
    // adb shell am broadcast -a com.aradhana.capturecam.TEST_FOCUS
    // --ef x 0.5 --ef y 0.5
    private val testFocusReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val x = intent.getFloatExtra("x", 0.5f).coerceIn(0f, 1f)
            val y = intent.getFloatExtra("y", 0.5f).coerceIn(0f, 1f)
            sonyProduction.autofocus(x, y) { ok ->
                Log.i(TAG, "testFocusReceiver: x=$x y=$y ok=$ok")
            }
        }
    }
    // End-to-end DSLR shutter/download/burst verification without mutating
    // tag, phase, upload, or operator-review state.
    private val testSonyCaptureReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (activeCameraSource != ProductionCameraSource.SONY) {
                Log.w(TAG, "testSonyCaptureReceiver: Sony is not active")
                return
            }
            val burstFrames = intent.getIntExtra("burstFrames", 1).coerceIn(1, 10)
            if (burstFrames > 1) {
                val useSmallProxies = intent.getBooleanExtra("smallProxies", false)
                Log.i(
                    TAG,
                    "testSonyCaptureReceiver: starting diagnostic native burst " +
                        "frames=$burstFrames smallProxies=$useSmallProxies"
                )
                sonyProduction.testBurst(burstFrames, useSmallProxies) { result ->
                    Log.i(
                        TAG,
                        "testSonyCaptureReceiver: burst result success=${result?.success} " +
                            "requested=${result?.requestedFrames} holdMs=${result?.holdMs} " +
                            "objectAdded=${result?.objectAddedEvents} retrieved=${result?.retrievedFrames} " +
                            "readyPeak=${result?.readyCountPeak} selected=${result?.selectedFrameIndex} " +
                            "scores=${result?.sharpnessScores?.map { "%.1f".format(it) }} " +
                            "selectedBytes=${result?.selectedImage?.size} " +
                            "restoredSingle=${result?.restoredSingleShot} error=${result?.error}"
                    )
                }
                return
            }
            captureFullRes { bytes ->
                val bounds = bytes?.let {
                    val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                    BitmapFactory.decodeByteArray(it, 0, it.size, options)
                    "${options.outWidth}x${options.outHeight}"
                }
                Log.i(TAG, "testSonyCaptureReceiver: bytes=${bytes?.size} dimensions=$bounds")
            }
        }
    }
    // Read-only diagnostic for whether Sony exposes card objects in Remote mode.
    // adb shell am broadcast -a com.aradhana.capturecam.TEST_SONY_CARD_OBJECTS
    private val testSonyCardObjectsReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            sonyProduction.probeCardObjects { result ->
                Log.i(
                    TAG,
                    "testSonyCardObjectsReceiver: storages=${result?.storageIds?.map { "0x${it.toString(16)}" }} " +
                        "total=${result?.totalHandles} newest=${result?.newestObjects} error=${result?.error}"
                )
            }
        }
    }
    private var angle1Jpeg: ByteArray? = null
    // Angle-2 positioning overlap (2026-08-26, explicit product decision):
    // the operator starts turning the item for angle 2 the instant angle
    // 1's physical shutter fires, instead of waiting ~5s for the original
    // to download. angle1Validated/angle1NeedsRetake gate the ACTUAL angle-2
    // shutter (not the positioning prompt) until angle 1's async not-moved
    // check has resolved -- see fireAngle2WhenAngle1Ready(). If it comes
    // back bad, the operator is redirected to retake angle 1 whenever that
    // result lands, even if they've already started repositioning.
    private var angle1Validated = false
    private var angle1NeedsRetake = false
    private var angle2Jpeg: ByteArray? = null
    // Set for the whole MAIN-accepted -> angle1 -> angle2 sequence. tickJewel()
    // keeps running on its own timer the entire time phase stays JEWEL (which
    // it does until the sequence finishes and calls resetForNewItem(Phase.TAG))
    // -- without this guard it kept re-arming and re-firing captureJewel()
    // mid-sequence, starting a SECOND overlapping angle sequence that raced
    // the first one, sending contradictory BLE commands to the gimbal and
    // occasionally corrupting a capture (bytes=null). This was the real cause
    // of "works on item 1, breaks on item 2" -- item 2 inherited whatever mess
    // the race left behind.
    private var inAngleSequence = false
    // One Sony original may take several seconds to transfer. Prevent an
    // immediate null callback from recursively launching hundreds of new
    // shutters while the previous capture lane is still returning to Live
    // View. Retries are delayed and bounded instead.
    private var angleCaptureInFlight = false
    private var angleCaptureRetryCount = 0
    // Set while the READY button is showing, waiting for the staff to
    // confirm the ornament is positioned for this angle's shot; null the
    // rest of the time so an accidental late tap does nothing.
    private var pendingReadyAction: (() -> Unit)? = null
    // Net whole-tick nudges applied by attemptCenteringCorrection(), signed
    // (positive = toward AXIS_CENTER+CENTERING_DEFLECTION direction on that
    // axis). Tracked so the exact opposite total can be undone in one move
    // at the end of the item -- these are velocity commands, so "centered"
    // isn't a position we can just command back to directly.
    // Signed CUMULATIVE move-time (ms) applied to each axis by centering +
    // hunting this item, positive = toward AXIS_CENTER+CENTERING_DEFLECTION
    // direction. ms, not a tick count -- centering nudge duration is
    // proportional to how far off-center the object is (see
    // centeringDurationFor()), so a plain nudge COUNT can no longer tell
    // the undo how long to run; total accumulated time can.
    private var centeringPanMs = 0
    private var centeringTiltMs = 0
    private var centeringAttempts = 0

    // Last-known upright-normalized center of the locked gold object, used
    // by bestGoldObjectBox() to reject a same-tick jump onto an unrelated
    // gold cluster elsewhere in frame (see MAX_TARGET_JUMP). Reset whenever
    // tracking restarts for a new item/angle so a fresh search isn't
    // artificially constrained to the previous item's position.
    private var lockedBoxCenter: android.graphics.PointF? = null
    // Rotation MaterialDetector's points were sampled in for THIS tick --
    // needed by bestObjectBox() to convert its points into the same
    // upright-normalized space latestObjectBoxesUpright already uses.
    @Volatile private var lastMaterialRotationDegrees = 0

    private enum class CenterAxis { NONE, PAN, TILT }
    // Which axis the LAST centering nudge moved, its sign, and its actual
    // duration -- lets the next call detect "that nudge just lost the
    // ornament" and undo precisely that move (same duration) rather than
    // guessing a fixed one.
    private var lastCenterAxis = CenterAxis.NONE
    private var lastCenterSign = 0
    private var lastCenterDurationMs = 0
    // Set for exactly one subsequent attempt after a revert, so centering
    // tries the OTHER axis first instead of immediately re-trying the one
    // that just overshot.
    private var centerAvoidAxis = CenterAxis.NONE

    // ---- Blind search (MAIN only): active only before anything has ever
    // been detected for this item -- see huntStep(). Deterministic sweep
    // order per explicit spec: DOWN first, then level->LEFT, then
    // center->RIGHT, stopping the instant gold is found at any point.
    private enum class HuntPhase { SCAN_DOWN, RETURN_TILT, SCAN_LEFT, RETURN_PAN, SCAN_RIGHT, GIVE_UP }
    private var huntPhase = HuntPhase.SCAN_DOWN
    private var huntPhaseMsSpent = 0
    private var huntBusy = false
    private var huntStartedAt = 0L
    // Set after a full down/left/right sweep finds nothing -- without this,
    // GIVE_UP fed straight back into the grace timer and restarted the
    // WHOLE sweep every ~800ms forever ("hunts forever" -- confirmed live).
    // A real pause after a genuine miss gives the operator a chance to
    // reposition the item and lets a passive detection (no sweep needed)
    // still arm normally in the meantime.
    private var huntCooldownUntil = 0L

    private val prefs by lazy { getSharedPreferences("capturecam", MODE_PRIVATE) }

    private fun serverUrl(): String {
        val stored = prefs.getString("server_url", DEFAULT_SERVER_URL)
            ?.trim()?.ifEmpty { DEFAULT_SERVER_URL } ?: DEFAULT_SERVER_URL
        // The old Ethernet-only address fails when its cable is removed.
        // Windows mDNS publishes this host on both Ethernet and Wi-Fi, so
        // Android re-resolves the active interface without operator edits.
        return if (stored.equals(LEGACY_ETHERNET_SERVER_URL, ignoreCase = true)) {
            DEFAULT_SERVER_URL
        } else {
            stored
        }
    }
    private val handler = Handler(Looper.getMainLooper())
    // Restrict ML Kit to formats used by stock labels. Scanning every format
    // made one Sony bitmap analysis occupy the scanner for roughly 5 seconds.
    private val barcodeScanner by lazy {
        BarcodeScanning.getClient(
            BarcodeScannerOptions.Builder()
                .setBarcodeFormats(
                    Barcode.FORMAT_QR_CODE,
                    Barcode.FORMAT_DATA_MATRIX,
                    Barcode.FORMAT_CODE_128,
                    Barcode.FORMAT_CODE_39
                )
                .build()
        )
    }
    // Conversion and Task listeners stay off the main/UI looper. Default ML
    // Kit listeners were starved behind the 25fps ImageView renderer, leaving
    // barcodeBusy latched for seconds even when native recognition had ended.
    private val barcodeExecutor: ExecutorService = Executors.newSingleThreadExecutor { runnable ->
        Thread({
            // THREAD_PRIORITY_DEFAULT, not _BACKGROUND (2026-08-28 fix): this
            // was set low back when every scan also ran OCR in parallel and
            // cost ~50ms -- now barcode-only (see the OCR-removal fix the
            // same day), each scan is ~10-20ms, and BACKGROUND priority made
            // the scheduler defer this thread behind other background work
            // on a 12GB/Snapdragon-7-Gen-2 tablet with plenty of headroom to
            // just run it promptly instead.
            android.os.Process.setThreadPriority(android.os.Process.THREAD_PRIORITY_DEFAULT)
            runnable.run()
        }, "CaptureCamBarcode").apply { isDaemon = true }
    }
    // Material analysis must never execute on SonyProductionLiveView. That
    // thread's only job is to drain/decode the newest camera frame. A
    // single-flight background lane drops obsolete analysis instead of
    // slowing the stream or building latency.
    private val jewelAnalysisExecutor: ExecutorService = Executors.newSingleThreadExecutor { runnable ->
        Thread({
            android.os.Process.setThreadPriority(android.os.Process.THREAD_PRIORITY_BACKGROUND)
            runnable.run()
        }, "CaptureCamJewelAnalysis").apply { isDaemon = true }
    }
    private val jewelAnalysisBusy = AtomicBoolean(false)
    // Lightweight on-device "Google Lens"-style object localizer -- a small
    // bundled TFLite model (no network, no server round-trip), the same
    // class of tech behind Lens's live object framing. Only gives coarse
    // categories (Fashion goods/Home goods/etc, not "necklace" specifically
    // -- that still needs the server-side Grounding DINO pass after
    // capture), but its bounding box is a genuine detected-object boundary,
    // not a color/contrast guess, so it's a strictly better fence for the
    // live dot overlay than MaterialDetector's heuristic alone.
    private val objectDetector by lazy {
        ObjectDetection.getClient(
            ObjectDetectorOptions.Builder()
                .setDetectorMode(ObjectDetectorOptions.STREAM_MODE)
                .enableMultipleObjects()
                .build()
        )
    }
    @Volatile private var objectDetectBusy = false
    // Normalized (0..1) against the UPRIGHT (rotation-applied) frame --
    // same space ML Kit itself returns boxes in. See uprightPoint() for why
    // MaterialDetector's raw sensor-space points need converting before
    // they can be tested against these.
    @Volatile private var latestObjectBoxesUpright: List<RectF> = emptyList()

    // ---- Pipeline state (mirrors capture.html's module-level _quality* vars) ----
    private enum class Phase { JEWEL, TAG, UPLOADING }
    // TAG now runs FIRST (2026-08-18, task #76: scan the tag before the
    // jewel photos, not after) -- default phase and every fresh-item entry
    // point below changed from JEWEL to TAG to match.
    private var phase = Phase.TAG
    private var armed = false
    private var armedAt = 0L
    private var stepFocusAttempts = 0
    private var maxUsableZoom = Float.MAX_VALUE
    // 0L = not currently stuck. Set the first tick meetsHardCaptureRules()
    // finds itself at maxUsableZoom (not the hardware zoom ceiling) with
    // occupancy still below CAPTURE_MIN_OCCUPANCY -- see that function's
    // own doc comment for why this distinction matters.
    private var maxUsableZoomStuckSince = 0L
    // Timestamp of the last actual zoom change (climb step or backoff
    // step) -- ZOOM_SETTLE_MS after this is the earliest focus may be
    // triggered/judged; ZOOM_STEP_INTERVAL_MS after this is the earliest
    // another climb step may be taken. See tickJewel.
    private var lastZoomChangeAt = 0L
    // Current auto-exposure bias, in whole EV stops -- persists across
    // ticks so applyAutoExposure() can step it incrementally rather than
    // recomputing from scratch every time. Reset per item (see
    // resetForNewItem) so a piece that needed a heavy negative bias
    // doesn't leave the NEXT item starting under-exposed.
    private var autoExposureEv = 0f
    private var lastExposureAdjustAt = 0L
    private var exposureClipStreak = 0
    private var exposureClearStreak = 0
    private var exposureCommandInFlight = false
    private var pendingAutoExposureEv: Float? = null
    private var manualExposureOverride = false
    // Manual zoom override: true only after staff uses zoom +/-. Exposure
    // adjustment and tap/long-press focus are compatible with automatic
    // capture and must not silently stop it (confirmed live 2026-08-24).
    // While true,
    // tickJewel()'s entire auto-tracking/zoom-climb/exposure/capture path
    // stands down -- staff is flying the camera by hand, and auto mode
    // fighting that input would be actively harmful (exactly the class of
    // problem "manual override" was asked for). Cleared only by an
    // explicit tap on resumeAutoButton, never automatically, so staff
    // always knows which mode they're in. Reset to false per item in
    // resetForNewItem so a manual session on one piece doesn't silently
    // carry into the next.
    private var manualModeActive = false
    // Set by a long-press-to-focus-lock; while true, continuous AF
    // tracking's region-steering (updateTrackingRegionFor) is skipped so
    // the manually-locked focus point doesn't get silently re-aimed.
    // Cleared alongside manualModeActive.
    private var manualFocusLocked = false
    // Smoothed centre estimate used ONLY by meetsHardCaptureRules()'s
    // centering check -- raw bounds/mlBox centre jitters far more than the
    // deadband itself for small/split objects (confirmed live 2026-08-18:
    // a stud-earring pair's union bounds swung cx between ~0.43 and ~0.59
    // tick to tick, a stationary piece that never actually moved). Without
    // smoothing, a single lucky noisy frame can land inside
    // CENTERING_DEADBAND purely by chance and the shutter fires on it --
    // that's what "captures off-center every time" actually was, not a
    // failure to ever attempt centering. EMA damps single-frame spikes
    // while still tracking a real, sustained gimbal move within a few
    // ticks. Reset per item in resetForNewItem so a stale estimate from
    // the previous item/phase can't gate the next one.
    private var centerEmaCx: Float? = null
    private var centerEmaCy: Float? = null
    // Explicit settle deadline for centering nudges. rsc2.isMoving alone
    // isn't enough: RSC2Controller.streamDeflection() clears
    // activeMoveRunnable (which isMoving reads) the INSTANT the stop frame
    // is sent, then separately waits settleMs (400ms default) before
    // calling its own onDone -- attemptCenteringCorrection() never used
    // that callback (fired with an empty lambda, returned immediately), so
    // isMoving alone would still let the next tick read a frame from
    // during that 400ms physical settle window. This timestamp covers the
    // full durationMs+settleMs window explicitly. Reset to 0 per item.
    private var centeringSettledUntil = 0L
    // Divergence circuit-breaker for attemptCenteringCorrection(). Confirmed
    // live (2026-08-18): a coordinate-axis bug made pan nudges push dx
    // MONOTONICALLY LARGER for 18 consecutive corrections (0.06 -> 0.13),
    // then tilt did the same in the other direction and drove the gimbal
    // into its physical tilt hard-stop. The axis bug itself got reverted,
    // but nothing in this function was ever checking "is this actually
    // helping" -- it just kept issuing same-direction nudges as long as the
    // deadband test kept failing, with no floor on how bad "not helping"
    // could get before stopping. This tracks the error magnitude from the
    // last nudge on each axis; if the next nudge on the SAME axis doesn't
    // measurably reduce it, that axis is treated as non-convergent for the
    // rest of this item and centering gives up on it rather than continuing
    // to push. Reset per item in resetForNewItem.
    private var lastNudgeAxis = CenterAxis.NONE
    private var lastNudgeErrorMagnitude: Float? = null
    private var centerDivergeStreak = 0
    // Whether a decisive AF trigger has already been sent for the CURRENT
    // zoom level -- the single-shot discipline that stops AF being
    // re-triggered every tick while waiting for its result.
    private var focusTriggeredThisLevel = false
    private var focusEvaluationNotBefore = 0L
    // Hard circuit breaker for automatic RemoteTouchOperation requests in
    // one physical pose. Detector/ROI oscillation must never restart Sony AF
    // indefinitely. Staff tap-to-focus bypasses this budget deliberately.
    private var sonyAutomaticAfCommandsForPose = 0
    // True while a smoothZoomTo() ramp is actively running -- tickJewel
    // must not judge focus, take another step, or capture while the zoom
    // is still physically moving. Set false when the ramp reaches target.
    private var isZooming = false
    // Set the instant MAX_STALL_MS first expires, so the safety valve below
    // gets one last forced re-focus attempt instead of shuttering on
    // whatever frame happens to be live at that exact millisecond.
    private var stallGraceAt = 0L
    // Consecutive ticks with no material detected -- see its use in
    // tickJewel's "lost the piece" branch for why this exists.
    private var materialLossStreak = 0
    // One-shot per item: whether the "too close to focus" warning has
    // already extended the stall clock once. Prevents it from looping
    // forever if the piece genuinely never gets moved back.
    private var tooCloseWarned = false
    private var readyStreak = 0
    // Local-AI shape fallback (2026-08-28, AiAdvisor.kt) -- fires ONE
    // advisory call after wrongShape has persisted a while (not every
    // tick: that would hammer the shared local Ollama instance for no
    // benefit), and if it agrees the framing roughly matches the
    // category, temporarily lets capture proceed despite the geometric
    // aspect-ratio mismatch. Scoped to wrongShape only, never edgeClipped
    // -- a physically-clipped item needs a shorter distance, not a second
    // opinion. Keyed to resolvedCategoryKey so a different item after this
    // one never inherits a stale override.
    private var wrongShapeSince = 0L
    private var aiShapeAdviceInFlight = false
    private var aiShapeAdviceCategory: String? = null
    private var aiShapeOverrideUntil = 0L
    // True right after tag capture, before MAIN's auto-detect/hunt loop is
    // allowed to run -- per explicit request: placing the item under the
    // camera takes real time, and starting the hunt/timer immediately on
    // tag confirm meant the gimbal could start sweeping for nothing before
    // staff had even walked over. tickJewel() no-ops entirely while this
    // is true; cleared by the READY button tap, same pattern as
    // promptForSideProfile()'s gate before angle1/angle2.
    private var jewelReadyPending = false
    private var angleStableStreak = 0
    private var angleStableRefocusAttempts = 0
    // One decisive Sony AF request per settled side-angle pose. The angle
    // retry loop used to issue RemoteTouchOperation every ~1.57s whenever a
    // non-focus capture gate (usually occupancy/centering) still failed,
    // repeatedly driving an already-sharp lens through a new AF sweep.
    // Re-arm only after the operator changes angle or this method actually
    // moves the gimbal/zoom.
    private var angleFocusTriggered = false
    // EMA of the physical stand-distance ratio. Updated on the UI thread
    // from Sony detector results; smoothing stops a stationary stand from
    // flickering CLOSER/FARTHER as reflective highlights change its box.
    private var standDistanceRatioEma: Float? = null
    // Full-frame locate -> centered category ROI -> full-frame recovery.
    // Volatile because Sony analysis and the main capture tick use separate
    // executors. Never stays locked after a missed target.
    @Volatile private var compositionRoiLocked = false
    // Bounds how many zoom-in steps centerThenCapture() will take chasing
    // CAPTURE_MIN_OCCUPANCY for ONE angle shot -- reset per side (see
    // promptForSideProfile), not per item.
    private var angleZoomRounds = 0
    private var jewelCaptureRetries = 0
    private var jewelJpeg: ByteArray? = null
    private var tagJpeg: ByteArray? = null
    private var tagCodeHistory = mutableListOf<String>()
    @Volatile private var stableTagCode: String? = null
    private data class TagBurstSample(val code: String?, val jpeg: ByteArray?)
    private data class TagBurstOutcome(
        val active: Boolean,
        val progress: Int,
        val winner: String? = null,
        val evidenceJpeg: ByteArray? = null,
        val failed: Boolean = false,
        val started: Boolean = false
    )
    private val tagBurstLock = Any()
    private val tagBurstSamples = mutableListOf<TagBurstSample>()
    @Volatile private var tagBurstActive = false
    @Volatile private var tagBurstProgress = 0
    private var confirmedTagEvidenceJpeg: ByteArray? = null
    // Hard pre-capture category gate. A decoded label is not accepted until
    // the catalogue server confirms its exact category.
    private var resolvedCategoryKey: String? = null
    private var categoryResolutionCode: String? = null
    private var categoryResolutionError: String? = null
    private var invalidTagCode: String? = null
    // Stud/rhodium-accent status (2026-08-19, explicit request). Null
    // means "not yet fetched/no correction on record" -- the live UI falls
    // back to studAutoGuess in that case. Once studFlagPersisted is
    // non-null (either fetched from the server or set by a staff tap), it
    // wins over the auto-guess -- a human correction should not keep
    // getting silently overwritten by a flickering per-frame guess.
    private var studFlagPersisted: Boolean? = null
    private var studAutoGuess: Boolean = false
    private var studFlagFetchInFlight = false
    private var autoFired = false
    private var lastAnalysisAt = 0L
    @Volatile private var latestSonyPreviewBitmap: Bitmap? = null
    private val sonyPreviewUpdatePending = AtomicBoolean(false)
    private var displayedSonyPreviewBitmap: Bitmap? = null
    private var lastPreviewRenderAtElapsed = 0L
    private var nextPreviewRenderAtElapsed = 0L
    private val sonyPreviewRenderRunnable = object : Runnable {
        override fun run() {
            if (isDestroyed || activeCameraSource != ProductionCameraSource.SONY) {
                sonyPreviewUpdatePending.set(false)
                return
            }
            val newest = latestSonyPreviewBitmap
            if (newest != null && newest !== displayedSonyPreviewBitmap) {
                binding.sonyPreviewView.setImageBitmap(newest)
                displayedSonyPreviewBitmap = newest
            }
            // fpsGraph samples THIS tick's own cadence, not Sony's raw
            // arrival rate (2026-08-28 fix) -- this loop already holds the
            // latest-wins frame at a fixed interval regardless of source
            // jitter, so this is what the operator actually sees on
            // screen. A real stall (GC pause, UI thread jank) still shows
            // up here as a dip; source-side network/shutter jitter no
            // longer does, since it's already absorbed by the latest-wins
            // slot above.
            // Handler.postAtTime schedules against SystemClock.uptimeMillis,
            // NOT elapsedRealtime -- both timing and scheduling below use
            // uptimeMillis so they stay on the same clock.
            val nowUptime = SystemClock.uptimeMillis()
            if (lastPreviewRenderAtElapsed != 0L) {
                val deltaMs = nowUptime - lastPreviewRenderAtElapsed
                if (deltaMs > 0) binding.fpsGraph.addSample(1000f / deltaMs)
            }
            lastPreviewRenderAtElapsed = nowUptime
            // Present latest-wins frames at an even 25fps cadence. Sony's
            // network JPEGs arrive in small bursts; posting every arrival
            // directly made 22-25 average FPS still look visibly jerky.
            // Scheduled against a fixed absolute clock, not "40ms from
            // whenever this run() happened to execute" (2026-08-28 fix):
            // postDelayed's relative scheduling lets any single late tick
            // (a GC pause, a busy main-looper queue) push every following
            // tick back by the same amount, compounding into visible drift
            // over time. postAtTime targets fixed points on the clock, so a
            // late tick is a one-off blip that self-corrects on the next
            // one instead of dragging the whole cadence off schedule.
            if (nextPreviewRenderAtElapsed == 0L) nextPreviewRenderAtElapsed = nowUptime
            nextPreviewRenderAtElapsed += SONY_PREVIEW_RENDER_INTERVAL_MS
            if (nextPreviewRenderAtElapsed <= nowUptime) nextPreviewRenderAtElapsed = nowUptime + SONY_PREVIEW_RENDER_INTERVAL_MS
            handler.postAtTime(this, nextPreviewRenderAtElapsed)
        }
    }
    // True while the post-capture preview (image + Retake/Cancel) is on
    // screen -- tickJewel/tickTag must not act on new frames underneath it,
    // or the pipeline could re-fire another auto-capture while the operator
    // is still looking at the last one.
    private var previewShowing = false
    private var previewCountdownRunnable: Runnable? = null
    private var previewGeneration = 0L
    private var capturePreviewBitmap: Bitmap? = null

    @Volatile private var latestMaterial: MaterialDetector.Result? = null
    @Volatile private var lastSonyMaterialPresent = false
    @Volatile private var sonyItemDetectedAtNanos = 0L
    @Volatile private var sonyFocusLockedForItem = false
    @Volatile private var latestSharpness: Float = 0f
    @Volatile private var barcodeBusy = false
    // Single-flight barcode analysis can safely reuse these buffers until
    // ML Kit's completion callback releases barcodeBusy. This removes the
    // old full-frame IntArray + NV21 allocations from every scan.
    private var barcodeScaledBitmap: Bitmap? = null
    private var barcodeArgbBuffer = IntArray(0)
    private var barcodeNv21Buffer = ByteArray(0)
    private val barcodeScalePaint = Paint(Paint.FILTER_BITMAP_FLAG)
    private var lastTrackingLogAt = 0L
    private var lastCenterLimitLogAt = 0L
    @Volatile private var barcodeAttempts = 0
    @Volatile private var lastBarcodeCount = -1
    @Volatile private var lastBarcodeError: String? = null

    companion object {
        private const val TAG = "CaptureCam"
        private val TAG_CODE_PATTERN = Regex("^[A-Za-z]{1,8}[0-9]{0,4}[/_-][0-9]+$")
        private const val PREF_CAMERA_MODE = "camera_mode_index"
        // Fallback seed only, used when no IP has been discovered/persisted
        // yet (a truly fresh install) -- SonyCameraDiscovery tries this
        // first, then falls through to a full subnet sweep if it's stale,
        // so an out-of-date value here never blocks connection, just costs
        // one quick failed attempt. Updated 2026-08-29 (was .14, camera has
        // since moved to .20) so a fresh install doesn't pay that cost.
        private const val SONY_CAMERA_IP = "192.168.0.20"
        private const val SONY_SSH_USER = "pkANY7"
        private val CAMERA_MODE_LABELS = arrayOf(
            "DSLR — Sony ZV-E10 II",
            "Smartphone camera"
        )
        private const val SONY_MIN_ZOOM_RATIO = 1f
        // 16-50mm PZ lens fitted to the deployed ZV-E10 II: 50/16.
        private const val SONY_MAX_ZOOM_RATIO = 3.125f
        // Measured full 16->50mm power-zoom travel. AUTO must use the same
        // physical ZoomOperation press/release path as the proven +/- buttons;
        // ZoomScale can ACK without changing the optical Live View image.
        private const val SONY_ZOOM_FULL_TRAVEL_MS = 1_650f
        // Endpoint reset deliberately runs slightly longer than measured
        // travel. This removes accumulated position-estimate error and lets
        // the lens's own endpoint stop guarantee true 16mm/full-wide.
        private const val SONY_ZOOM_WIDE_ENDPOINT_HOLD_MS = 1_800L
        private const val SONY_ZOOM_WIDE_RESET_MAX_ATTEMPTS = 3
        // Short Sony ZoomOperation press/release pulse for each manual tap.
        // About 7% of the 16-50mm lens travel: fine enough for framing while
        // remaining visibly responsive.
        private const val SONY_MANUAL_ZOOM_PULSE_MS = 120L
        private const val SONY_MANUAL_ZOOM_MAX_QUEUED_STEPS = 3
        private const val SONY_MANUAL_ZOOM_BUSY_RETRIES = 3
        private val SONY_PROFILE_LABELS = arrayOf(
            "Jewellery detail (recommended)",
            "Camera full auto",
            "Custom"
        )
        private val SONY_ISO_LABELS = arrayOf("Auto", "ISO 100", "ISO 200", "ISO 400", "ISO 800")
        private val SONY_ISO_VALUES = intArrayOf(0x00FF_FFFF, 100, 200, 400, 800)
        private val SONY_EXPOSURE_MODE_LABELS = arrayOf(
            "Auto", "Program (P)", "Aperture priority (A)", "Shutter priority (S)", "Manual (M)"
        )
        private val SONY_EXPOSURE_MODE_VALUES = intArrayOf(294_912, 65_538, 131_075, 196_612, 1)
        private val SONY_APERTURE_LABELS = arrayOf(
            "Camera/current", "f/4", "f/5.6", "f/8", "f/11", "f/16"
        )
        private val SONY_APERTURE_VALUES = arrayOf<Int?>(null, 400, 560, 800, 1_100, 1_600)
        private val SONY_SHUTTER_LABELS = arrayOf(
            "Camera/current", "1/30", "1/60", "1/100", "1/125", "1/160", "1/200", "1/250"
        )
        private val SONY_SHUTTER_VALUES = arrayOf<Pair<Int, Int>?>(
            null, 1 to 30, 1 to 60, 1 to 100, 1 to 125, 1 to 160, 1 to 200, 1 to 250
        )
        private val SONY_WB_LABELS = arrayOf(
            "Auto", "Daylight", "Tungsten", "Flash", "Fluorescent warm",
            "Fluorescent cool", "Fluorescent day white", "Fluorescent daylight",
            "Cloudy", "Shade", "Underwater auto"
        )
        private val SONY_WB_VALUES = intArrayOf(
            2, 4, 6, 7, 0x8001, 0x8002, 0x8003, 0x8004, 0x8010, 0x8011, 0x8030
        )
        private val SONY_FOCUS_MODE_LABELS = arrayOf("AF-C", "AF-S", "AF-A", "DMF", "Manual")
        private val SONY_FOCUS_MODE_VALUES = intArrayOf(0x8004, 2, 0x8005, 0x8006, 1)
        private val SONY_FOCUS_AREA_LABELS = arrayOf(
            "Flexible Spot L", "Wide", "Zone", "Tracking: Zone", "Tracking: Spot L"
        )
        private val SONY_FOCUS_AREA_VALUES = intArrayOf(259, 1, 2, 514, 518)
        private const val SONY_JEWEL_FOCUS_AREA_TRACKING_SPOT_L = 518
        private val SONY_METERING_LABELS = arrayOf(
            "Multi", "Center-weighted", "Entire screen average", "Spot", "Highlight"
        )
        private val SONY_METERING_VALUES = intArrayOf(0x8001, 0x8002, 0x8003, 0x8004, 0x8006)
        private val SONY_FILE_FORMAT_LABELS = arrayOf(
            "RAW + JPEG (recommended)", "JPEG only", "RAW only"
        )
        private val SONY_FILE_FORMAT_VALUES = intArrayOf(2, 3, 1)
        private val SONY_RAW_TYPE_LABELS = arrayOf(
            "Lossless compressed (recommended)", "Compressed"
        )
        private val SONY_RAW_TYPE_VALUES = intArrayOf(6, 1)
        private val SONY_JPEG_QUALITY_LABELS = arrayOf(
            "Extra Fine", "Fine", "Standard", "Light"
        )
        private val SONY_JPEG_QUALITY_VALUES = intArrayOf(1, 2, 3, 4)
        private val SONY_IMAGE_SIZE_LABELS = arrayOf("L (maximum)", "M", "S")
        private val SONY_IMAGE_SIZE_VALUES = intArrayOf(1, 2, 3)
        private val SONY_TRANSFER_SIZE_LABELS = arrayOf(
            "Original JPEG (required for catalogue)", "Small review JPEG"
        )
        private val SONY_TRANSFER_SIZE_VALUES = intArrayOf(1, 2)
        private val SONY_ASPECT_RATIO_LABELS = arrayOf("3:2 (full sensor)", "16:9", "4:3", "1:1")
        private val SONY_ASPECT_RATIO_VALUES = intArrayOf(1, 2, 3, 4)
        private val SONY_DRO_LABELS = arrayOf("Off (controlled light)", "Auto", "Level 1", "Level 2", "Level 3", "Level 4", "Level 5")
        private val SONY_DRO_VALUES = intArrayOf(1, 31, 17, 18, 19, 20, 21)
        private val SONY_CREATIVE_LOOK_LABELS = arrayOf(
            "Standard", "Portrait", "Neutral", "Vivid", "Vivid 2", "Film",
            "Instant", "Soft High-key", "Black & White", "Sepia"
        )
        private val SONY_CREATIVE_LOOK_VALUES = intArrayOf(1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
        // Production requirement: deterministic colour/geometry detection
        // only. Never connect the retired local DINO/WebSocket experiment.
        private const val DINO_SERVO_ENABLED = false
        private const val SONY_MIN_EXPOSURE_EV = -5f
        private const val SONY_MAX_EXPOSURE_EV = 5f
        // Guide-box area caps coverage at roughly 0.435 (the blob's box can
        // never exceed the 64%x68% guide region it's measured within) --
        // 0.10 was reachable almost immediately at 1x for any reasonably
        // close item, so the climb rarely ran at all ("doesn't zoom, clicks
        // from far away"). 0.24 asks for the piece to fill about half the
        // guide box before settling, which actually uses the climb.
        private const val MIN_LIVE_COVERAGE = 0.24f
        // How many CONSECUTIVE ticks with material=false before the
        // "lost the piece" zoom-backoff actually fires. See its use in
        // tickJewel -- a single flickered false reading (common on small,
        // shiny pieces under reflective lighting) must not discard a real
        // zoom climb in progress.
        private const val MATERIAL_LOSS_GRACE_TICKS = 4
        // Set FALSE (2026-08-18) per explicit request: gold colour
        // detection alone, no ML Kit object box. See its call site in
        // onFrame and bestObjectBox()'s short-circuit below.
        private const val ML_KIT_OBJECT_DETECTION_ENABLED = false
        // Non-negotiable hard capture gate (user requirement): the ornament
        // must occupy at least this fraction of the FULL frame, and be
        // centered, or nothing fires -- not even the stall-safety-valve.
        // Checked against ML Kit's real object box specifically, NOT
        // MaterialDetector's coverage -- that colour-heuristic metric is
        // measured within a 64%x68% guide region and mathematically caps
        // out around 0.435, so it can never express "75% of the frame" no
        // matter how tight the framing actually is. ML Kit's box is
        // reported in full-frame-normalized space and has no such cap.
        // If ML Kit hasn't found a box at all, this rule fails closed
        // (can't verify compliance -> don't capture) rather than falling
        // back to a metric that can't represent the requirement.
        private const val CAPTURE_MIN_OCCUPANCY = 0.75f
        // How long meetsHardCaptureRules() holds off accepting a small
        // frame caused by a maxUsableZoom focus-failure backoff (see its
        // own doc comment) before falling back to the old accept-anyway
        // behaviour. Long enough for staff to notice and nudge the item
        // back from the lens; short enough not to meaningfully slow a
        // genuinely stuck item down relative to the old always-accept path.
        private const val MAX_USABLE_ZOOM_GRACE_MS = 6000L
        private const val MAX_FOCUS_RETRIES = 2
        // 50->16mm in 1/1.25 backoff steps needs at most six AF checks.
        // Seven remains a finite hard wall while allowing the full ladder.
        private const val MAX_AUTOMATIC_AF_COMMANDS_PER_POSE = 7
        private const val FOCUS_EVALUATION_DELAY_MS = 1_000L
        private const val ZOOM_BACKOFF_RATIO = 0.8f
        // Below this zoom, a "lost the piece" reading only pauses the climb
        // (holds current zoom, waits) instead of backing off -- at low zoom
        // the frame is wide enough that a stationary, gimbal-centered piece
        // physically can't have "walked out of frame," so a loss reading
        // there is far more likely a detection glitch than a real framing
        // problem. See its use in tickJewel's material-loss branch.
        private const val ZOOM_BACKOFF_MIN_ZOOM = 1.5f
        // Real barcode scanning re-enabled for production (2026-08-18) --
        // was true only for JEWEL-flow testing, where a placeholder
        // "TEST-<timestamp>" tag code stood in for a real scan.
        private const val SKIP_BARCODE_FOR_TESTING = false
        // PROVISIONAL, not yet calibrated -- see looksUnrotated()'s doc
        // comment. Mean per-cell grayscale difference (0-255 scale) below
        // which two angle shots are considered near-duplicates (item
        // likely wasn't actually rotated between them).
        private const val UNROTATED_MEAN_DIFF_THRESHOLD = 8.0
        // Larger closed-loop steps reduce costly Sony HTTP/control-pipeline
        // transitions while retaining detection feedback after every step.
        // 1.4, not 1.25 (2026-08-28 fix): the zoom MOTOR itself is already
        // continuous -- driveZoom is a single velocity-driven power-zoom
        // pulse whose duration scales with distance (see
        // setCameraZoomRatio's holdMs calc). The "robotic" feel reported
        // live was the CLIMB pausing to re-evaluate after every 1.25x hop,
        // each followed by a mandatory ZOOM_SETTLE_MS pause -- a real
        // 4-5-stop climb from 1.0x to ~3x read as several visible
        // start-stop jerks rather than one sweep. A larger per-step ratio
        // means fewer hops (and fewer pauses) to cover the same distance,
        // without removing the safety re-check between steps (coverage/
        // focus/centering/edge-clip are still re-read after every one).
        private const val ZOOM_STEP_RATIO = 1.4f
        private const val ZOOM_STEP_INTERVAL_MS = 250L
        private const val CAPTURE_PREVIEW_SECONDS = 2
        private const val PREVIEW_DECODE_MAX_EDGE = 4096
        private const val ANGLE_CAPTURE_MAX_RETRIES = 6
        private const val ANGLE_CAPTURE_RETRY_DELAY_MS = 350L
        // Auto-exposure (2026-08-18): steps exposure compensation down
        // when too much of the GOLD area is blown out (specular
        // reflections eating engraving/facet detail), back up toward 0
        // once it isn't. Rate-limited and small-stepped on purpose --
        // this rides on top of the camera's own AE_MODE_ON metering, not
        // a replacement for it, so it should nudge gently rather than
        // hunt. Threshold picked conservatively (needs real calibration
        // against labeled over/under-exposed examples, same caveat as
        // every other uncalibrated threshold in this file): above 12% of
        // gold samples clipped is treated as "losing detail," below 4%
        // is treated as "clearly fine, safe to recover brightness."
        // Between the two, hold steady rather than react to noise.
        // Tightened (2026-08-18): 700ms/0.33EV/12% never produced a
        // visible change during a real capture -- confirmed the control
        // itself works (direct EV override at -2.0 was dramatic and
        // immediate), so the auto-trigger was simply too slow/conservative
        // to matter within a normal few-second framing window. 400ms/0.5EV
        // reaches a visible -1.0EV within ~1s of triggering instead of
        // ~2s. HIGHLIGHT_CLIP_HIGH dropped from 12%->3%: sceneClipFraction
        // is computed over the WHOLE sampled region (dark stand/jewellery
        // included, not just the bright background), which dilutes the
        // ratio a lot -- 12% of the ENTIRE frame reading near-white is a
        // much higher bar than "the background looks washed out."
        // More aggressive still (2026-08-18, explicit request): bigger
        // steps, faster cadence, deeper floor -- gold clipping at all
        // should pull exposure down hard and fast, not creep toward it.
        // Restored to production's exact tuned values (2026-08-26): this
        // candidate branch had detuned every dimension of this reactive
        // corrector -- smaller step (1/3 EV vs 1.0), shallower floor (-2.0
        // vs -4.0), slower Sony interval (500ms vs 600ms... note interval
        // itself got FASTER not slower, see below), and replaced the
        // production two-signal trigger (gold-clip-at-all OR whole-scene
        // clip) with a gold-only trigger requiring 8% of gold samples
        // clipped -- gold samples are sparse per frame (production's own
        // 2026-08-18 comment already root-caused this exact failure mode),
        // so in practice it almost never fired. Confirmed live: goldClip
        // read 0.0 on every tick during a real E2E test while the operator
        // reported the image was visibly too bright.
        private const val EXPOSURE_ADJUST_INTERVAL_MS = 250L
        private const val SONY_EXPOSURE_ADJUST_INTERVAL_MS = 600L
        private const val EXPOSURE_STEP_EV = 1.0f
        private const val EXPOSURE_MIN_EV = -4.0f
        private const val HIGHLIGHT_CLIP_HIGH = 0.03f
        private const val HIGHLIGHT_CLIP_LOW = 0.01f
        private const val MIN_TRUSTED_TARGET_AREA = 0.004f
        private const val MIN_TRUSTED_GOLD_POINTS = 12
        private const val TRACKING_LOG_INTERVAL_MS = 1_000L
        // Quiet time required after ANY zoom change (a climb step or a
        // backoff step) before focus is triggered or judged at all. Camera2
        // AF triggered while the lens/sensor is still settling from a zoom
        // change is judged on a moving target -- this is the actual fix for
        // "focus hunting too rapid": the previous code re-triggered AF on
        // literally every zoom step during the climb (a new trigger every
        // ~150ms interrupted whatever partial scan the last one started),
        // which reads as the lens racking rapidly and never converging.
        private const val ZOOM_SETTLE_MS = 450L
        private const val MAX_STALL_MS = 12_000L
        // Baked-in default so staff never have to see or fill in a server
        // URL -- confirmed reachable (2026-08-19). Settings still allows
        // overriding it (e.g. a different LAN IP if the laptop changes),
        // but the app now works correctly out of the box with zero setup.
        private const val DEFAULT_SERVER_URL = "https://ARADHANA.local:7660"
        private const val LEGACY_ETHERNET_SERVER_URL = "https://192.168.0.7:7660"
        // ~1.5s total grace before treating the gimbal as truly disconnected
        // (see waitForGimbalReady's caller doc comment).
        private const val GIMBAL_READY_GRACE_ATTEMPTS = 5
        private const val GIMBAL_READY_GRACE_INTERVAL_MS = 300L
        // Blank counts as "not configured" too -- SharedPreferences' own
        // getString(key, default) only substitutes the default when the KEY
        // is entirely absent, not when it's present but blank (confirmed
        // live 2026-08-19: an earlier empty Settings save left the key
        // sitting at "" forever, so the intended default never took over).
        private const val TICK_INTERVAL_MS = 150L
        private const val SONY_PREVIEW_RENDER_INTERVAL_MS = 40L
        // 8.3fps keeps the Sony preview at its 25fps target. Live testing at
        // 80ms reduced preview to 20-21fps; focus, not scan cadence, was the
        // real tag-lock bottleneck. Two-frame confirmation remains ~240ms.
        private const val SONY_TAG_ANALYSIS_INTERVAL_MS = 60L
        // Preserve the Sony stream's full width. Small printed labels lost
        // too many finder/edge pixels when reduced to 640px.
        private const val SONY_TAG_ANALYSIS_LONG_EDGE = 1024
        private const val SONY_TAG_BURST_FRAMES = 5
        private const val SONY_TAG_BURST_MAJORITY = 3
        private const val SONY_JEWEL_ANALYSIS_INTERVAL_MS = 80L
        private const val SONY_TAG_FOCUS_AREA_WIDE = 1
        private const val SHARPNESS_THRESHOLD = 40f
        // physId=4 from logCameraDiagnostics's real dump on this exact
        // phone (2026-08-19): 5.56mm, closestFocus~10cm -- the macro-
        // capable sensor. physId=3 (12.19mm "telephoto") only focuses down
        // to ~40cm, unusable for jewellery work; physId=2 is the ultra-wide.
        // Device-specific by construction (a different phone's logical
        // camera would enumerate different physical IDs) -- bindUseCasesPinned
        // already fails open to the unpinned default if this ID doesn't
        // exist/isn't accepted, so a phone swap degrades gracefully rather
        // than breaking the camera outright.
        private const val MACRO_PHYSICAL_CAMERA_ID = "4"
        // Below this, autofocus isn't "struggling" -- it never converged at
        // all. Real-world observed range for a genuinely too-close subject
        // was ~2-4 (see the sharpness=2.0-4.3 readings that forced a soft
        // capture through the old stall valve); 15 is well above that noise
        // floor but still well below SHARPNESS_THRESHOLD*0.6 (24).
        private const val TOO_CLOSE_SHARPNESS_FLOOR = 15f
        private const val REQUIRED_READY_TICKS = 3
        // Fixed test values for the RSC 2 3-angle workflow -- NOT real
        // per-category calibration yet. Single-axis pan sweep: center -> pan
        // LEFT one step (angle 1) -> pan RIGHT two steps, crossing back
        // through center to the mirrored right-side position (angle 2) ->
        // pan LEFT one step, returning to true center for the next item.
        // "Step" is expressed as a fixed deflection held for PAN_STEP_MS,
        // not a calibrated degree value -- these are velocity commands (see
        // RSC2Controller), so travelled angle is deflection x time.
        //
        // Axis mapping fully confirmed 2026-08-17 via isolated one-axis
        // tests (see RSC2Controller's doc comment): axis1=tilt, axis2=roll,
        // axis3=pan.
        //
        // ANGLE_1/ANGLE_2 no longer use a scripted gimbal pan sweep -- the
        // staff physically rotates the ornament itself to show each side
        // profile (a real rotation of the piece, which a camera pan around
        // a stationary object can't replicate), taps READY when it's
        // positioned, and the gimbal's job becomes fine RE-CENTERING via
        // tilt/pan on wherever the piece ended up, not a preset sweep.
        private const val ANGLE_STABLE_TIMEOUT_MS = 4500L
        private const val ANGLE_STABLE_TICKS = 3
        private const val ANGLE_STABLE_REFOCUS_ATTEMPTS = 3
        // Conservative live-zoom cap per the "physical distance should do
        // most of the framing" principle -- pushing digital/hybrid zoom
        // much past this loses detail the catalogue pipeline later wants.
        // Reverted to 3.4 (2026-08-18) after the >3.4x focus test.
        private const val MAX_LIVE_ZOOM_RATIO = 3.4f
        // Auto-centering (runs before MAIN, using axis1=tilt/axis3=pan --
        // confirmed mapping, see RSC2Controller). Gentler deflection than
        // the angle sweep since this is fine correction, not a deliberate
        // wide angle change. IMPORTANT LIMITATION: these are velocity
        // commands, not absolute-position commands (see RSC2Controller's
        // moveOut/returnHome doc) -- there is no "move to X degrees", only
        // "move this direction for this long". Centering therefore works by
        // small bounded nudges + re-measuring, not a single calculated
        // move, and each nudge is tracked in whole ticks so the exact
        // opposite total can be undone in one shot at the end of the item.
        private const val CENTERING_DEFLECTION = 120
        private const val CENTERING_DEADBAND = 0.06f
        // Ported from the DINO/MIL branch's VisionServoController
        // (2026-08-18): "zoom-IN only once roughly centered" -- looser than
        // CENTERING_DEADBAND deliberately, this only gates whether the
        // climb may take its NEXT step at all, not full capture-readiness.
        // That branch's own doc comment: "confirmed live: a target still
        // far off-center got zoomed to 3.4x while pan/tilt were still
        // catching up, clipping it at the frame edge and getting the whole
        // servo stuck (large error that never shrinks, because the object
        // is partially out of frame, not because the direction is wrong)."
        // This is the same failure shape observed repeatedly tonight in
        // this file's own zoom-climb logs (drift getting WORSE as zoom
        // climbed, magnifying an already-uncorrected off-center error) --
        // that branch had already designed around it; this just adopts the
        // same guard here. Requiring full centering before any zoom step
        // would stall framing progress on a target that's close-but-not-
        // perfect, hence looser than the capture deadband.
        // Loosened 0.15 -> 0.25 (2026-08-28, requested: zoom and gimbal
        // feeling like one coordinated operator instead of two sequenced
        // ones): this guard's own doc comment above says the failure it
        // exists to prevent IS an object getting clipped at the frame edge
        // while zoom races ahead of centering -- that exact outcome is now
        // caught directly by tickJewel's edgeClipped check (added the same
        // day), which halts the zoom climb the moment a box touches an
        // edge, regardless of this deadband. That doesn't make this guard
        // pointless -- a target can still drift progressively worse off-
        // center under zoom without ever touching an edge -- so this is a
        // moderate loosening, not a removal: zoom joins the centering
        // motion sooner (needs live confirmation it still converges
        // smoothly, not oscillating, before loosening further).
        private const val ZOOM_ALLOW_DEADBAND = 0.25f
        // Follow-the-gold rule (2026-08-28): how far off-center the
        // tracked box may be before zoom actively retreats to give
        // centering room, instead of climbing in on a still-off-center
        // target. Looser than ZOOM_ALLOW_DEADBAND (which only gates
        // whether zoom-IN may proceed) -- this triggers an active zoom-OUT
        // step, a stronger action reserved for genuinely bad offsets.
        private const val FOLLOW_GOLD_ZOOM_OUT_DEADBAND = 0.32f
        // Starting estimate, needs live tuning (2026-08-28): how much of
        // the top of frame to exclude from material/exposure analysis for
        // NECK_CURVE items pinned to max zoom-out, to keep the physical
        // ring light above the rail out of sceneClipFraction and blob
        // detection. Too small and the light still leaks in; too large
        // and it starts cropping the necklace's own top connector tabs
        // out of the ANALYSIS region (framing/capture itself is unaffected
        // either way -- this only trims what gets analysed, not what the
        // Sony sensor captures).
        private const val RING_LIGHT_EXCLUDE_TOP_FRACTION = 0.12f
        // AiAdvisor shape-fallback pacing (2026-08-28): wait this long into
        // a continuous wrongShape run before spending a round trip on the
        // shared local Ollama instance, then don't ask again for a full
        // cooldown even if still wrong-shaped -- a transient misread
        // shouldn't trigger a call, and a firm "no" shouldn't be re-asked
        // every tick. AI_SHAPE_OVERRIDE_MS is how long a "yes" is trusted
        // before the geometric gate resumes having the final word.
        private const val WRONG_SHAPE_AI_FALLBACK_MS = 1_500L
        private const val WRONG_SHAPE_AI_COOLDOWN_MS = 6_000L
        private const val AI_SHAPE_OVERRIDE_MS = 4_000L
        // Max upright-normalized distance a newly-selected gold box may be
        // from the previously locked one and still be accepted as "the same
        // object" -- generous enough for real tick-to-tick movement/zoom,
        // tight enough to reject a jump onto an unrelated gold cluster
        // (e.g. a display case) elsewhere in frame. See bestGoldObjectBox().
        private const val MAX_TARGET_JUMP = 0.35f
        // Nudge duration scales with how far off-center the object is
        // (centeringDurationFor()): CENTERING_TICK_MS at a small offset,
        // climbing linearly to CENTERING_TICK_MS_MAX at a half-frame
        // (0.5) offset. A fixed 200ms nudge was proven far too weak live:
        // logged offsets barely moved across 8 consecutive same-direction
        // nudges (dx stuck around -0.45 to -0.43 the whole attempt budget)
        // -- CENTERING_DEFLECTION(120) x 200ms is roughly 10x less
        // cumulative "push" than the old confirmed-working pan sweep
        // (250 x 900ms), nowhere near enough to close a large offset.
        private const val CENTERING_TICK_MS = 200L
        private const val CENTERING_TICK_MS_MAX = 900L
        private const val CENTERING_MAX_ATTEMPTS = 12
        // Angle shots reuse the same centering primitive but need a bigger
        // budget: staff places the piece by hand after rotating it, which
        // can start much further off-center than MAIN's fine pre-capture
        // correction ever has to travel from.
        private const val ANGLE_CENTERING_MAX_ATTEMPTS = 12
        // Angle shots have no independent zoom-climb loop like MAIN's
        // tickJewel -- centerThenCapture() does bounded manual zoom steps
        // toward CAPTURE_MIN_OCCUPANCY instead, capped so a piece that
        // genuinely can't reach 75% at this distance doesn't zoom forever.
        private const val ANGLE_ZOOM_MAX_ROUNDS = 6
        // DJI's published RSC 2 mechanical range (dji.com/support/product/
        // rsc-2): pan is a 360° continuous slip-ring (no hard limit -- safe
        // to sweep freely), roll is -240..+95, tilt is -112..+214. Roll is
        // never commanded in production (axis2, confirmed unused). Only
        // tilt (axis1) can actually hit a hard mechanical stop from
        // anything this app sends.
        //
        // PROVISIONAL cap, not yet calibrated: we don't have a live
        // ms-to-degrees conversion for this rig (no absolute-position
        // feedback over BLE, only velocity commands), so this is a
        // deliberately conservative total-move-time budget -- small
        // relative to the ~326° total tilt range -- rather than a value
        // derived from real testing. Needs a live one-axis sweep-to-
        // hard-stop test (same technique used to confirm axis mapping) to
        // replace this with an actual degree-based limit.
        // Raised from 2400 (2026-08-18): confirmed live this was too
        // conservative for a real starting position -- centering hit this
        // ceiling while the item was still well off-center, gave up, and
        // let zoom climb anyway with no further gimbal correction. Still a
        // placeholder, still well under the ~326° full range, just less
        // prematurely restrictive.
        // Raised again 5000 -> 9000 (2026-08-18): both budgets are
        // CUMULATIVE across MAIN + angle1 + angle2 for one item (by
        // design -- undoCenteringThenAdvance() needs the running total to
        // undo it in one shot at item end), but angle1/angle2 each
        // involve the operator physically turning the piece to a very
        // different pose, which can legitimately need a large fresh
        // correction on top of whatever MAIN already used. Confirmed live:
        // stuck on angle2 with "pan budget exhausted (ms=4704)" and no way
        // to finish centering, even though the axis genuinely still
        // needed correcting (not a runaway -- MAX_TARGET_JUMP and the
        // gold-only target selection are the actual runaway guards, this
        // budget is just a BLE-churn/pathological-case backstop).
        private const val TILT_MS_LIMIT = 9000
        // Pan has no mechanical hard-stop the way tilt does (full 360°
        // rotation), but still needs a budget cap -- see the doc comment at
        // its call site in attemptCenteringCorrection() for why (target-jump
        // runaway, 2026-08-18). Same order of magnitude as TILT_MS_LIMIT.
        private const val PAN_MS_LIMIT = 9000
        // Production safety hardwall (2026-08-24 E2E, BL18/33): a brief
        // detector miss armed the old targetless DOWN/LEFT/RIGHT sweep after
        // only 800ms. It spent ~6000ms tilting down before colour detection
        // recovered even though the ornament was physically in view. The
        // camera must never move without a verified target. Keep huntStep()
        // for controlled diagnostics, but production waits stationary for a
        // real detection; target-guided fine centering remains enabled.
        private const val AUTONOMOUS_BLIND_HUNT_ENABLED = false
        // Blind search (huntStep()) -- only runs before anything has ever
        // been detected for this item. Bigger, longer steps than fine
        // centering (CENTERING_*) since this is covering ground, not
        // fine-tuning. Short grace (not zero) so a single bad frame right
        // at arm-time doesn't kick off a full sweep -- "as soon as the
        // shot starts" per spec, not a long wait.
        private const val HUNT_GRACE_MS = 800L
        private const val HUNT_STEP_DEFLECTION = 180
        private const val HUNT_STEP_MS = 500L
        // "All the way down" for tilt is bounded by TILT_MS_LIMIT (the
        // real mechanical-limit safety budget) rather than a literal
        // hard-stop sweep. "All the way left/right" for pan has no such
        // mechanical limit (DJI spec: pan is a 360° continuous slip-ring),
        // so this is a deliberately generous practical search arc instead
        // -- not literally 360°, which would be impractical for a fixed
        // camera rig.
        private const val HUNT_PAN_SWEEP_MAX_MS = 8000
        // Real pause after a full sweep finds nothing, before trying again
        // automatically -- prevents the "hunts forever" restart loop.
        private const val HUNT_COOLDOWN_MS = 6000L

        // ---- DINO+MIL tracking pipeline (checkpoint build) ----
        // Master switch for the whole pipeline. Set FALSE (2026-08-18) per
        // explicit request: go back to the legacy colour+ML-Kit detection
        // path for production instead of the DINO/MIL vision servo, which
        // is still unfinished/unreliable (capture stays hard-disabled
        // whenever this is true regardless). The DINO+MIL work itself is
        // untouched and left in place on the checkpoint-dino-mil-rsc2-
        // 2026-08-17 branch for whenever it's picked back up.
        private const val TRACKING_PIPELINE_ACTIVE = false
        private const val DETECTOR_SEND_INTERVAL_MS = 120L
        private const val DETECTOR_FRAME_LONG_EDGE = 960
        private const val DETECTOR_JPEG_QUALITY = 75
        private const val SERVO_INTERVAL_MS = 130L
        private const val SERVO_MIN_MS = 90L
        private const val SERVO_MAX_MS = 260L
        private const val SERVO_MAX_DEFLECTION = 220
        private const val ZOOM_SERVO_INTERVAL_MS = 250L
        private const val GIMBAL_RETRY_INTERVAL_MS = 5_000L
        private const val MAX_GIMBAL_PERMISSION_PROMPTS = 3
    }

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        cameraPermissionRequestInFlight = false
        if (granted && requestedCameraMode() == RequestedCameraMode.SMARTPHONE) {
            startCamera()
        } else if (!granted && requestedCameraMode() == RequestedCameraMode.SMARTPHONE) {
            Toast.makeText(
                this,
                "Camera permission required for Smartphone mode",
                Toast.LENGTH_LONG
            ).show()
            setStatus("Smartphone camera permission required", ready = false)
        }
    }

    // Best-effort, silent RSC 2 connect -- fails open (single-image mode)
    // if permissions are denied or no gimbal is found; never blocks the
    // camera pipeline on this. Self-heals: if the gimbal is off/out of
    // range/not yet paired at launch, scheduleGimbalRetry keeps quietly
    // re-trying in the background (matching DetectorClient's own
    // Handler.postDelayed reconnect pattern) so it upgrades to 3-angle
    // capture automatically the moment the gimbal becomes reachable,
    // without the operator needing to restart the app.
    private val requestBlePermissions = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { _ ->
        // Never call attemptGimbalConnect() directly from here. Confirmed
        // live production crash (2026-08-21): on this device, this
        // callback reported every permission granted, but
        // ContextCompat.checkSelfPermission in attemptGimbalConnect still
        // reported the same ones missing right after -- calling it inline
        // re-launched the request, whose callback called it again, forever,
        // synchronously (no dialog shown, no frame yielded back to the
        // user), until the stack overflowed. Routing through
        // scheduleGimbalRetry defers the next attempt onto the Handler
        // queue instead of the current call stack, so this exact loop can
        // never recur regardless of why the permission states disagree.
        scheduleGimbalRetry(immediate = true)
    }

    private var gimbalPermissionPromptCount = 0
    private var gimbalRetryScheduled = false
    @Volatile private var mainScreenActive = false

    private fun attemptGimbalConnect() {
        if (!mainScreenActive || rsc2.isReady) return
        val needed = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= 31) {
            needed += Manifest.permission.BLUETOOTH_SCAN
            needed += Manifest.permission.BLUETOOTH_CONNECT
        } else {
            needed += Manifest.permission.ACCESS_FINE_LOCATION
        }
        val missing = needed.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            // Cap how many times the system permission dialog itself gets
            // shown -- an operator who's denied it a few times shouldn't
            // get nagged on every resume. The CONNECTION retry below still
            // keeps running regardless, in case permission is later granted
            // from Settings without ever seeing another in-app prompt.
            if (gimbalPermissionPromptCount < MAX_GIMBAL_PERMISSION_PROMPTS) {
                gimbalPermissionPromptCount++
                requestBlePermissions.launch(missing.toTypedArray())
            }
            scheduleGimbalRetry()
            return
        }
        rsc2.connect(this) { success ->
            Log.i(TAG, if (success) "RSC 2 connected -- 3-angle capture enabled" else "No RSC 2 found -- single-image mode")
            if (!success) scheduleGimbalRetry()
        }
    }

    private fun scheduleGimbalRetry(immediate: Boolean = false) {
        if (!mainScreenActive || rsc2.isReady || gimbalRetryScheduled) return
        gimbalRetryScheduled = true
        handler.postDelayed({
            gimbalRetryScheduled = false
            attemptGimbalConnect()
        }, if (immediate) 0L else GIMBAL_RETRY_INTERVAL_MS)
    }

    // True when launched via the capturecam://start deep link from
    // capture.html, rather than tapped from the launcher directly. Drives
    // whether a successful upload hands control back to the browser
    // (finish()) or loops internally for the next item -- see uploadPair.
    private var launchedFromBrowser = false

    // Guards the one-time "arm a fresh TAG scan + start the tick loop" work
    // in startCamera() -- see its doc comment. startCamera() runs on every
    // onResume() and camera-error rebind, not just true cold start.
    private var pipelineStarted = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        OpenCvKcfProbe.run()
        // This is a kiosk-style capture station -- the operator's hands are
        // usually busy holding jewellery/tags, not touching the screen, so
        // an unexpected sleep mid-workflow (requiring a touch + possibly a
        // PIN to recover) is actively disruptive. Explicit flag rather than
        // relying on system sleep settings/wake locks being configured
        // correctly on every deployed device.
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        launchedFromBrowser = intent?.data?.scheme == "capturecam"

        binding.settingsButton.setOnClickListener { showSettingsDialog() }
        // Long-press entry point for reviewing background-upload rejections
        // (2026-08-26 fix): needs_review items were previously only ever
        // surfaced as a transient Toast with no way to act on them -- the
        // settings neutral-button slot is already used by RSC2 BLE test,
        // so this uses long-press instead of a new dialog button.
        binding.settingsButton.setOnLongClickListener { showUploadReviewDialog(); true }
        binding.manualShutterButton.setOnClickListener { forceCaptureCurrentPhase() }
        binding.readyButton.setOnClickListener {
            val action = pendingReadyAction ?: return@setOnClickListener
            hideReadyButton()
            action()
        }
        setupManualControls()

        sonyProduction = SonyProductionCamera(
            context = applicationContext,
            onFrame = ::onSonyFrame,
            onAvailabilityChanged = ::onSonyAvailabilityChanged
        )
        // NOT wired to fpsGraph (2026-08-28 fix): this fires at Sony's raw
        // frame-arrival cadence, which is inherently jittery -- network
        // bursts plus the shutter-speed/live-view-rate link documented on
        // SonyProductionCamera. Feeding that straight to the on-screen
        // graph made a perfectly smooth preview look like it was stuttering
        // (18-25fps swings) when the actual DISPLAYED image was already
        // locked to a steady 25fps by sonyPreviewRenderRunnable below --
        // confirmed live, the graph was reporting the wrong layer. Kept
        // available for engineering logcat use if a future change needs
        // raw source-side cadence again.
        sonyProduction.onFrameTiming = { }
        // Persists a rediscovered camera IP (2026-08-28) so the NEXT launch
        // starts at the last-known-good address instead of a stale one --
        // see SonyCameraDiscovery's doc comment for why this is needed at
        // all. Fires on a background thread; SharedPreferences.edit() is
        // thread-safe to call from anywhere.
        sonyProduction.onCameraIpChanged = { newIp ->
            prefs.edit().putString("sony_camera_ip", newIp).apply()
            Log.i(TAG, "Sony camera IP updated to $newIp after rediscovery")
        }
        // Last-known-good capture_server.py address from a prior rediscovery
        // sweep (see triggerServerRediscovery) -- tried before mDNS/static
        // fallback on this launch too, not just after a fresh failure.
        prefs.getString("capture_server_ip", null)?.let { UploadClient.discoveredServerIp = it }
        CaptureUploadQueue.resumePending(applicationContext)
        ensurePipelineStarted()
        applyRequestedCameraMode(allowPermissionPrompt = true)

        // See RSC2Controller.onUnexpectedDisconnect's doc comment: without
        // this, a mid-session BLE drop (range/interference/OS hiccup --
        // normal for any BLE peripheral) never got retried until the
        // Activity happened to pause/resume for some unrelated reason,
        // which read as the gimbal being permanently dead until an app
        // restart. This routes it back into the same self-heal loop the
        // initial connect uses.
        rsc2.onUnexpectedDisconnect = {
            Log.w(TAG, "RSC 2 disconnected unexpectedly -- resuming self-heal retry loop")
            scheduleGimbalRetry(immediate = true)
        }

        attemptGimbalConnect()
        connectDetector()
        // EXPORTED (not NOT_EXPORTED) deliberately -- this needs to be
        // reachable from `adb shell am broadcast`, which runs as a
        // different UID than this app. Debug-only test hook on a LAN-only
        // tool, not a production attack surface.
        val filter = IntentFilter("com.aradhana.capturecam.TEST_MOVE")
        val exposureFilter = IntentFilter("com.aradhana.capturecam.TEST_EXPOSURE")
        val zoomFilter = IntentFilter("com.aradhana.capturecam.TEST_ZOOM")
        val zoomMotorFilter = IntentFilter("com.aradhana.capturecam.TEST_ZOOM_MOTOR")
        val focusFilter = IntentFilter("com.aradhana.capturecam.TEST_FOCUS")
        val sonyCaptureFilter = IntentFilter("com.aradhana.capturecam.TEST_SONY_CAPTURE")
        val sonyCardObjectsFilter = IntentFilter("com.aradhana.capturecam.TEST_SONY_CARD_OBJECTS")
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(testMoveReceiver, filter, RECEIVER_EXPORTED)
            registerReceiver(testExposureReceiver, exposureFilter, RECEIVER_EXPORTED)
            registerReceiver(testZoomReceiver, zoomFilter, RECEIVER_EXPORTED)
            registerReceiver(testZoomMotorReceiver, zoomMotorFilter, RECEIVER_EXPORTED)
            registerReceiver(testFocusReceiver, focusFilter, RECEIVER_EXPORTED)
            registerReceiver(testSonyCaptureReceiver, sonyCaptureFilter, RECEIVER_EXPORTED)
            registerReceiver(testSonyCardObjectsReceiver, sonyCardObjectsFilter, RECEIVER_EXPORTED)
        } else {
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(testMoveReceiver, filter)
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(testExposureReceiver, exposureFilter)
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(testZoomReceiver, zoomFilter)
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(testZoomMotorReceiver, zoomMotorFilter)
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(testFocusReceiver, focusFilter)
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(testSonyCaptureReceiver, sonyCaptureFilter)
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(testSonyCardObjectsReceiver, sonyCardObjectsFilter)
        }
    }

    /**
     * With launchMode="singleTask", re-launching this app (tapping the
     * launcher icon again, or the capturecam://start deep link from
     * capture.html) while its task is already alive in the background does
     * NOT call onCreate again -- Android just brings the existing instance
     * forward and delivers the new Intent here instead. Without this
     * override that meant every "fresh" open actually resumed showing
     * whatever phase (e.g. "Scanning tag…") the PREVIOUS session had been
     * left on, with the pipeline's tick loop still running against stale
     * state -- indistinguishable from a hang from the operator's side, and
     * why "it's still looking for the tag" kept reproducing on a supposedly
     * new launch. Every entry from outside now forces a clean restart.
     */
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        launchedFromBrowser = intent.data?.scheme == "capturecam"
        // Same bug shape already found and fixed for bindUseCases()
        // (2026-08-19, see its own comment above) -- resetForNewItem(TAG)
        // wipes tagJpeg/stableTagCode but NOT jewelJpeg/angle1Jpeg/
        // angle2Jpeg, so any stray re-entry mid-item silently drops just
        // the tag while the jewel photos survive, producing exactly
        // "Missing photo or tag" at upload time with all 3 photos present.
        // THIS call site had the same unconditional reset and was missed
        // by that fix -- confirmed live (2026-08-19, tag WATI item):
        // browser capture.html re-firing capturecam://start (plausible
        // right after a server reconnect/page reload) while this app was
        // still mid-JEWEL with all 3 angles already shot. A genuinely
        // fresh item start (finished previous item, browser launches the
        // next one) always arrives with no unsaved jewel photos in
        // flight, so gating on that distinguishes "real new item" from
        // "stray duplicate re-entry" without needing to track intent
        // identity at all.
        val midItemWithUnsavedWork = jewelJpeg != null || angle1Jpeg != null || angle2Jpeg != null
        if (pipelineStarted && !midItemWithUnsavedWork) {
            resetForNewItem(Phase.TAG)
        } else if (midItemWithUnsavedWork) {
            Log.w(TAG, "onNewIntent ignored reset -- mid-item with unsaved jewel photo(s) in flight")
        }
        attemptGimbalConnect()
        if (::sonyProduction.isInitialized) applyRequestedCameraMode(allowPermissionPrompt = false)
    }

    override fun onResume() {
        super.onResume()
        mainScreenActive = true
        // Coming back to this screen (e.g. from the BLE diagnostics screen,
        // or after turning the gimbal on) is exactly when a previously
        // failed/never-attempted connect should be retried -- onCreate's
        // one-shot attempt otherwise never runs again for the rest of this
        // Activity's life. attemptGimbalConnect() already no-ops if already
        // connected, so this is safe to call on every resume.
        attemptGimbalConnect()
        if (::sonyProduction.isInitialized) applyRequestedCameraMode(allowPermissionPrompt = false)
    }

    override fun onPause() {
        mainScreenActive = false
        super.onPause()
    }

    // ---------------------------------------------------------------- Camera setup

    private fun startCamera() {
        if (::cameraProvider.isInitialized) {
            if (activeCameraSource == ProductionCameraSource.SONY) {
                suspendPhoneCameraForSony()
            } else {
                bindUseCases()
            }
            ensurePipelineStarted()
            return
        }
        if (cameraProviderRequestInFlight) return
        cameraProviderRequestInFlight = true
        val providerFuture = ProcessCameraProvider.getInstance(this)
        providerFuture.addListener({
            cameraProviderRequestInFlight = false
            cameraProvider = providerFuture.get()
            if (activeCameraSource == ProductionCameraSource.SONY) {
                suspendPhoneCameraForSony()
            } else {
                bindUseCases()
            }
            // Only the very first bind should arm a fresh TAG/QR scan and
            // start the tick loop -- startCamera() also runs on every
            // onResume() (screen lock/unlock, a notification, switching
            // away and back) and from the capture-error rebind in
            // captureFullRes(). Before this fix, bindUseCases() itself
            // unconditionally called resetForNewItem(Phase.TAG), which
            // wipes tagJpeg/stableTagCode but NOT jewelJpeg/angle1Jpeg/
            // angle2Jpeg (those only clear on next==Phase.JEWEL) -- so any
            // resume or transient capture error mid angle1/angle2 silently
            // discarded the tag while the jewel photos survived untouched.
            // Confirmed live (2026-08-19): a real capture with all 3 jewel
            // photos present but stableTagCode null at upload time, which
            // is exactly this shape. A rebind after this point now only
            // rebuilds the CameraX pipeline, never touches capture state.
            ensurePipelineStarted()
            logCameraDiagnostics()
            logExtensionsDiagnostics()
        }, ContextCompat.getMainExecutor(this))
    }

    private fun ensurePipelineStarted() {
        if (pipelineStarted) return
        pipelineStarted = true
        resetForNewItem(Phase.TAG)
        handler.post(tickRunnable)
    }

    private fun requestedCameraMode(): RequestedCameraMode {
        val modes = RequestedCameraMode.values()
        return modes[prefs.getInt(PREF_CAMERA_MODE, 0).coerceIn(0, modes.lastIndex)]
    }

    /**
     * Hard camera boundary. DSLR mode never starts or falls back to CameraX;
     * a missing Sony blocks capture while SonyProductionCamera self-heals.
     * Smartphone mode stops Sony completely and binds CameraX exclusively.
     */
    private fun applyRequestedCameraMode(allowPermissionPrompt: Boolean) {
        val requestedMode = requestedCameraMode()
        val modeChanged = appliedCameraMode != requestedMode
        appliedCameraMode = requestedMode
        when (requestedMode) {
            RequestedCameraMode.DSLR -> {
                activeCameraSource = ProductionCameraSource.SONY
                binding.previewView.visibility = View.GONE
                if (::cameraProvider.isInitialized) suspendPhoneCameraForSony()
                if (!sonyProduction.isAvailable) {
                    binding.sonyPreviewView.visibility = View.GONE
                    if (phase != Phase.UPLOADING) {
                        setStatus("Sony camera restoring…", ready = false)
                    }
                }
                startSonyProduction()
                Log.i(TAG, "Camera mode=DSLR; phone fallback hard-disabled")
            }

            RequestedCameraMode.SMARTPHONE -> {
                activeCameraSource = ProductionCameraSource.PHONE
                // Stop once on entry. Repeated onResume/apply calls must not
                // generate redundant stop callbacks or transport churn.
                if (modeChanged) sonyProduction.stop()
                handler.removeCallbacks(sonyPreviewRenderRunnable)
                sonyPreviewUpdatePending.set(false)
                latestSonyPreviewBitmap = null
                displayedSonyPreviewBitmap = null
                lastPreviewRenderAtElapsed = 0L
                nextPreviewRenderAtElapsed = 0L
                binding.sonyPreviewView.setImageDrawable(null)
                binding.sonyPreviewView.visibility = View.GONE
                binding.previewView.visibility = View.VISIBLE
                ensurePhoneCameraStarted(allowPermissionPrompt)
                Log.i(TAG, "Camera mode=SMARTPHONE; Sony transport stopped")
            }
        }
        configureExposureSlider()
    }

    private fun ensurePhoneCameraStarted(allowPermissionPrompt: Boolean) {
        if (requestedCameraMode() != RequestedCameraMode.SMARTPHONE) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            startCamera()
            return
        }
        if (allowPermissionPrompt && !cameraPermissionRequestInFlight &&
            !cameraPermissionRequestedThisSession
        ) {
            cameraPermissionRequestInFlight = true
            cameraPermissionRequestedThisSession = true
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        } else {
            setStatus("Smartphone camera permission required", ready = false)
        }
    }

    private fun startSonyProduction() {
        if (requestedCameraMode() != RequestedCameraMode.DSLR) return
        val password = prefs.getString("sony_ssh_password", BuildConfig.SONY_SSH_PASSWORD)
            ?.takeIf { it.isNotBlank() }
            ?: BuildConfig.SONY_SSH_PASSWORD
        if (password.isBlank()) {
            Log.e(TAG, "Sony SSH password is not configured")
            setStatus("Sony camera credential missing", ready = false)
            return
        }
        val phaseFocusArea = if (phase == Phase.TAG) {
            SONY_TAG_FOCUS_AREA_WIDE
        } else {
            SONY_JEWEL_FOCUS_AREA_TRACKING_SPOT_L
        }
        sonyProduction.setStartupQualitySettings(
            savedSonyQualitySettings().copy(focusArea = phaseFocusArea)
        )
        sonyProduction.start(
            prefs.getString("sony_camera_ip", SONY_CAMERA_IP) ?: SONY_CAMERA_IP,
            prefs.getString("sony_ssh_user", SONY_SSH_USER) ?: SONY_SSH_USER,
            password
        )
    }

    /** Availability changes never cross the operator-selected hard boundary. */
    private fun onSonyAvailabilityChanged(available: Boolean, detail: String) {
        if (requestedCameraMode() != RequestedCameraMode.DSLR) {
            activeCameraSource = ProductionCameraSource.PHONE
            Log.i(TAG, "Ignoring Sony availability in Smartphone mode: $detail")
            return
        }
        // Remain SONY even while reconnecting. This is the hardwall that
        // prevents one item from silently mixing DSLR and phone frames.
        activeCameraSource = ProductionCameraSource.SONY
        if (available) {
            sonyZoomRatio = sonyProduction.currentZoomRatio()
            sonyZoomTarget = sonyZoomRatio
            queueAutoExposure(autoExposureEv)
            // resetForNewItem(TAG) can run before the Sony handshake is
            // ready. Availability is the authoritative moment to perform
            // the deferred full-wide endpoint reset; startup waiting never
            // consumes the bounded command-failure retry budget.
            if (phase == Phase.TAG && !wideResetComplete && !wideResetInFlight) {
                handler.post(::resetSonyZoomFullyWideForNextTag)
            }
        }
        Log.i(TAG, "Production camera=${activeCameraSource.name}: $detail")
        handler.post {
            if (isDestroyed) return@post
            binding.sonyPreviewView.visibility = if (available) View.VISIBLE else View.GONE
            binding.previewView.visibility = View.GONE
            suspendPhoneCameraForSony()
            if (available) {
                if (phase != Phase.UPLOADING) setStatus("Sony DSLR ready", ready = false)
            } else {
                handler.removeCallbacks(sonyPreviewRenderRunnable)
                sonyPreviewUpdatePending.set(false)
                lastPreviewRenderAtElapsed = 0L
                nextPreviewRenderAtElapsed = 0L
                if (phase != Phase.UPLOADING) setStatus(detail, ready = false)
            }
            configureExposureSlider()
        }
    }

    /** Runs the existing production detector/QR state against Sony frames. */
    private fun onSonyFrame(bitmap: Bitmap) {
        // The renderer samples this latest-wins slot at a fixed 25fps. Do
        // not mirror Sony's bursty network arrival cadence onto the UI.
        latestSonyPreviewBitmap = bitmap
        if (sonyPreviewUpdatePending.compareAndSet(false, true)) {
            handler.post(sonyPreviewRenderRunnable)
        }
        if (previewShowing || activeCameraSource != ProductionCameraSource.SONY) return
        val now = System.currentTimeMillis()
        // Preview and analysis have separate budgets. Barcode ML Kit and the
        // material detector do not need to run at display FPS; doing so used
        // 67% app CPU and visibly starved the preview/UI. Detection remains
        // responsive at 8.3fps (tag) / 12.5fps (jewellery).
        val analysisInterval = if (phase == Phase.TAG && tagBurstActive) {
            // During the bounded five-frame burst, decode every next distinct
            // frame as soon as the preceding ML task completes.
            0L
        } else if (phase == Phase.TAG) {
            SONY_TAG_ANALYSIS_INTERVAL_MS
        } else {
            SONY_JEWEL_ANALYSIS_INTERVAL_MS
        }
        if (now - lastAnalysisAt < analysisInterval) return
        lastAnalysisAt = now

        when (phase) {
            Phase.JEWEL -> {
                if (jewelAnalysisBusy.compareAndSet(false, true)) {
                    jewelAnalysisExecutor.execute {
                        try {
                            analyseSonyJewelFrame(bitmap)
                        } catch (e: Exception) {
                            Log.e(TAG, "Sony jewellery analysis failed", e)
                        } finally {
                            jewelAnalysisBusy.set(false)
                        }
                    }
                }
            }
            Phase.TAG -> {
                handler.post {
                    if (!isDestroyed) {
                        binding.boundsOverlay.update(emptyList(), 0, 0, 0)
                        clearStandDistanceGuide()
                    }
                }
                // Do not judge a label while the lens is still travelling to
                // its full-wide endpoint. Those first frames are blurred and
                // the simultaneous PTP zoom operation causes avoidable source
                // cadence gaps.
                if (!wideResetComplete || wideResetInFlight || barcodeBusy) return
                barcodeBusy = true
                barcodeAttempts += 1
                val attempt = barcodeAttempts
                val startedAt = System.nanoTime()
                // Exact camera JPEG paired with this decoded frame. Five are
                // only retained during a candidate burst (~200KB total).
                val sourceJpeg = sonyProduction.currentLiveViewJpeg()
                barcodeExecutor.execute {
                    try {
                        // Sony arrives as JPEG/Bitmap. Convert off the stream
                        // and UI threads to NV21 so ML Kit gets its native fast
                        // input path instead of internally converting Bitmap.
                        val barcodeFrame = bitmapToGrayscaleNv21(bitmap)
                        val preprocessedAt = System.nanoTime()
                        val input = InputImage.fromByteArray(
                            barcodeFrame.bytes, barcodeFrame.width, barcodeFrame.height, 0,
                            InputImage.IMAGE_FORMAT_NV21
                        )
                        // OCR (text recognizer) used to run alongside the
                        // barcode scanner on every frame here, but live
                        // testing (2026-08-28) showed its results were never
                        // used for acceptance (see the burst-rejection
                        // history below) while still doubling the per-frame
                        // ML/JPEG-decode cost -- confirmed via logcat as the
                        // direct cause of the tag-phase fps stutter and slow
                        // detection the operator reported. Dropped back to
                        // barcode-only. (Prior note, kept for context: OCR
                        // misreads a character (O/G/Z/2 confusion etc.)
                        // differently on almost every frame, and each misread
                        // still matches TAG_CODE_PATTERN's shape, producing a
                        // stream of near-miss votes that never agreed 3-of-5
                        // -- so merging OCR into acceptance was already ruled
                        // out before this fix removed it from the hot path
                        // entirely.)
                        val barcodeTask = barcodeScanner.process(input)
                        barcodeTask.addOnCompleteListener(barcodeExecutor) { _ ->
                                barcodeBusy = false
                                val elapsedMs = (System.nanoTime() - startedAt) / 1_000_000L
                                val prepMs = (preprocessedAt - startedAt) / 1_000_000L
                                val mlMs = elapsedMs - prepMs
                                val barcodes = if (barcodeTask.isSuccessful) barcodeTask.result.orEmpty() else emptyList()
                                val barcodeCodes = barcodes.mapNotNull { it.rawValue?.trim()?.takeIf(String::isNotEmpty) }
                                val codes = barcodeCodes.distinct()
                                if (codes.isNotEmpty() || attempt % 25 == 0) {
                                    Log.i(
                                        TAG,
                                        "Sony tag scan attempt=$attempt totalMs=$elapsedMs " +
                                            "prepMs=$prepMs mlMs=$mlMs barcodeResults=${barcodeCodes.size}"
                                    )
                                }
                                if (!barcodeTask.isSuccessful) {
                                    Log.w(TAG, "Sony barcode scan failed after ${elapsedMs}ms", barcodeTask.exception)
                                }
                                if (codes.isNotEmpty() || barcodeTask.isSuccessful) {
                                    val eligibleCodes = codes.filterNot { it == invalidTagCode }
                                    val outcome = consumeSonyTagBurst(eligibleCodes, sourceJpeg)
                                    handler.post {
                                        if (!isDestroyed && phase == Phase.TAG) {
                                            lastBarcodeCount = barcodes.size
                                            lastBarcodeError = null
                                            when {
                                                outcome.winner != null -> acceptSonyTagBurst(outcome)
                                                outcome.failed -> setStatus(
                                                    "Label changed or blurred — hold it steady",
                                                    ready = false
                                                )
                                                outcome.active -> setStatus(
                                                    "Confirming label ${outcome.progress}/$SONY_TAG_BURST_FRAMES…",
                                                    ready = false
                                                )
                                            }
                                        }
                                    }
                                } else {
                                    val error = barcodeTask.exception
                                    handler.post {
                                        lastBarcodeError = error?.message ?: error?.javaClass?.simpleName ?: "scan failed"
                                    }
                                }
                            }
                    } catch (e: Exception) {
                        barcodeBusy = false
                        Log.e(TAG, "Sony barcode preprocessing failed", e)
                        handler.post { lastBarcodeError = e.message ?: e.javaClass.simpleName }
                    }
                }
            }
            Phase.UPLOADING -> Unit
        }
    }

    /** First readable label starts a five-frame burst. Each incoming frame is
     * decoded immediately; no queue or five-frame wait is introduced. */
    private fun consumeSonyTagBurst(codes: List<String>, jpeg: ByteArray?): TagBurstOutcome =
        synchronized(tagBurstLock) {
            var started = false
            if (!tagBurstActive) {
                if (codes.isEmpty()) return@synchronized TagBurstOutcome(false, 0)
                tagBurstSamples.clear()
                tagBurstActive = true
                tagBurstProgress = 0
                started = true
                Log.i(TAG, "Sony tag five-frame burst started firstCodes=$codes")
            }

            val preferred = codes.firstOrNull { TAG_CODE_PATTERN.matches(it) }
                ?: codes.firstOrNull()
            tagBurstSamples += TagBurstSample(preferred, jpeg)
            tagBurstProgress = tagBurstSamples.size
            if (tagBurstSamples.size < SONY_TAG_BURST_FRAMES) {
                return@synchronized TagBurstOutcome(
                    active = true,
                    progress = tagBurstProgress,
                    started = started
                )
            }

            val vote = tagBurstSamples.mapNotNull { it.code }
                .groupingBy { it }
                .eachCount()
                .maxByOrNull { it.value }
            val winner = vote?.key?.takeIf { vote.value >= SONY_TAG_BURST_MAJORITY }
            val evidence = winner?.let { accepted ->
                // Middle matching frame is normally the steadiest evidence,
                // avoiding the operator's first-arrival/last-removal motion.
                val matches = tagBurstSamples.filter { it.code == accepted && it.jpeg != null }
                matches.getOrNull(matches.size / 2)?.jpeg
            }
            val votes = tagBurstSamples.map { it.code }
            tagBurstSamples.clear()
            tagBurstActive = false
            tagBurstProgress = 0
            if (winner == null) {
                Log.w(TAG, "Sony tag burst rejected votes=$votes")
                TagBurstOutcome(false, SONY_TAG_BURST_FRAMES, failed = true)
            } else {
                Log.i(TAG, "Sony tag burst accepted code=$winner votes=$votes")
                TagBurstOutcome(
                    active = false,
                    progress = SONY_TAG_BURST_FRAMES,
                    winner = winner,
                    evidenceJpeg = evidence
                )
            }
        }

    private fun acceptSonyTagBurst(outcome: TagBurstOutcome) {
        val code = outcome.winner?.trim()?.takeIf(String::isNotEmpty) ?: return
        if (phase != Phase.TAG || stableTagCode != null || code == invalidTagCode) return
        confirmedTagEvidenceJpeg = outcome.evidenceJpeg
        invalidTagCode = null
        tagCodeHistory = mutableListOf(code)
        stableTagCode = code
        resolveCategoryForCurrentTag()
    }

    private fun resetSonyTagBurst() {
        synchronized(tagBurstLock) {
            tagBurstSamples.clear()
            tagBurstActive = false
            tagBurstProgress = 0
        }
        confirmedTagEvidenceJpeg = null
    }

    /** Background-only consumer of the newest Sony frame. */
    private fun analyseSonyJewelFrame(bitmap: Bitmap) {
        val analysisStartedAt = System.nanoTime()
        val compositionProfile = CaptureCompositionProfiles.forCategory(resolvedCategoryKey)
        // A pair's union is centred in the frame but its centre is normally
        // empty space between the two ornaments. A small centred ROI therefore
        // alternated full-frame acquire -> empty ROI miss -> acquire on every
        // frame, and made both AF and the gimbal panic. Paired categories stay
        // full-frame; composition still uses their union midpoint.
        val supportsCenteredCompositionRoi = !isSplitPairProfile(compositionProfile)
        if (!supportsCenteredCompositionRoi) compositionRoiLocked = false
        val useCompositionRoi = armed && compositionRoiLocked &&
            compositionProfile != null && supportsCenteredCompositionRoi
        // Long items (NECK_CURVE) pin to max zoom-out (see tickJewel's
        // isLongItemCategory), which brings the physical ring light above
        // the TOP_RAIL into frame -- excluded from analysis so it can
        // neither feed sceneClipFraction (driving exposure down chasing a
        // brightness problem that isn't on the ornament) nor get
        // misclassified as part of the tracked blob (see this file's own
        // history of a display box's bright trim doing exactly that).
        val excludeTopFraction = if (compositionProfile?.silhouette ==
            CaptureCompositionProfiles.Silhouette.NECK_CURVE
        ) RING_LIGHT_EXCLUDE_TOP_FRACTION else 0f
        val result = MaterialDetector.analyse(
            bitmap,
            fullFrame = !useCompositionRoi,
            region = if (useCompositionRoi) compositionProfile?.detectorRegion() else null,
            excludeTopFraction = excludeTopFraction
        )
        latestMaterial = result
        // For paired jewellery, judge detail on one actual gold lobe. The old
        // union rectangle included the empty gap and could report a misleading
        // score unrelated to the surface Sony was supposed to focus.
        val focusTarget = jewelleryFocusTarget(result, compositionProfile)
        latestSharpness = focusTarget?.detailBounds
            ?.let { SharpnessAnalyzer.score(bitmap, it) } ?: 0f
        val cameraAssists = CameraAssistAnalyzer.analyse(bitmap, result.bounds)
        val present = isTrustedMaterialTarget(result)
        val resultBounds = result.bounds
        if (!present || resultBounds == null) {
            if (compositionRoiLocked) {
                compositionRoiLocked = false
                Log.i(TAG, "Composition ROI lost target; expanding to full-frame acquisition")
            }
        } else if (!compositionRoiLocked && compositionProfile != null &&
            supportsCenteredCompositionRoi
        ) {
            val cx = (resultBounds.x0 + resultBounds.x1) * 0.5f
            val cy = (resultBounds.y0 + resultBounds.y1) * 0.5f
            val roi = compositionProfile.detectorRegion()
            val goldInsideRoi = result.points.count {
                it.gold && it.x >= roi.x0 && it.x <= roi.x1 && it.y >= roi.y0 && it.y <= roi.y1
            }
            if (goldInsideRoi >= 3 &&
                kotlin.math.abs(cx - 0.5f) <= 0.10f &&
                kotlin.math.abs(cy - 0.5f) <= 0.10f
            ) {
                compositionRoiLocked = true
                Log.i(TAG, "Composition ROI locked category=${compositionProfile.categoryKey}")
            }
        }
        if (present != lastSonyMaterialPresent) {
            lastSonyMaterialPresent = present
            val detectedAt = System.nanoTime()
            Log.i(
                TAG,
                "Sony item presence=$present " +
                    "detectorMs=${(System.nanoTime() - analysisStartedAt) / 1_000_000L} " +
                    "coverage=${result.coverage} sharpness=$latestSharpness"
            )
            if (present) {
                sonyItemDetectedAtNanos = detectedAt
                sonyFocusLockedForItem = false
                // AF-C/Pre-AF handles acquisition. Do not interrupt Live View
                // with a touch-focus command on every detector transition.
            } else {
                sonyItemDetectedAtNanos = 0L
                sonyFocusLockedForItem = false
            }
        }
        val focus = sonyProduction.currentFocusIndication()
        if (present && !sonyFocusLockedForItem && (focus == 2 || focus == 6)) {
            val detectedAt = sonyItemDetectedAtNanos
            if (detectedAt != 0L) {
                sonyFocusLockedForItem = true
                Log.i(
                    TAG,
                    "Sony item focus locked detectToLockMs=" +
                        "${(System.nanoTime() - detectedAt) / 1_000_000L} " +
                        "focusIndication=$focus sharpness=$latestSharpness"
                )
            }
        }
        lastMaterialRotationDegrees = 0
        val goldPoints = result.points.filter { it.gold }
        val standGuidance = result.bounds?.let { bounds ->
            StandDistanceGuide.calculate(
                widthFraction = bounds.x1 - bounds.x0,
                heightFraction = bounds.y1 - bounds.y0,
                currentZoom = cameraZoomRatio(),
                maxZoom = SONY_MAX_ZOOM_RATIO,
                desiredArea = compositionProfile?.targetArea
                    ?: StandDistanceGuide.DESIRED_FRAME_AREA,
                targetAspect = compositionProfile?.normalizedFrameAspect
            )
        }
        handler.post {
            if (!isDestroyed && activeCameraSource == ProductionCameraSource.SONY) {
                binding.boundsOverlay.update(
                    goldPoints,
                    bitmap.width,
                    bitmap.height,
                    rotationDegrees = 0,
                    fitCenter = true
                )
                binding.boundsOverlay.updateCameraAssists(cameraAssists)
                binding.boundsOverlay.updateCameraFocus(
                    sonyFocusX,
                    sonyFocusY,
                    sonyProduction.currentFocusSnapshot()?.indication
                )
                renderStandDistanceGuide(standGuidance, compositionProfile)
            }
        }
    }

    private data class JewelleryFocusTarget(
        val x: Float,
        val y: Float,
        val detailBounds: MaterialDetector.Bounds
    )

    /** Keep pair composition centred on the pair, but focus and measure
     * detail on one real gold ornament rather than the empty midpoint. */
    private fun jewelleryFocusTarget(
        result: MaterialDetector.Result?,
        profile: CaptureCompositionProfiles.Profile? =
            CaptureCompositionProfiles.forCategory(resolvedCategoryKey)
    ): JewelleryFocusTarget? {
        val bounds = result?.bounds ?: return null
        val fallback = JewelleryFocusTarget(
            (bounds.x0 + bounds.x1) * 0.5f,
            (bounds.y0 + bounds.y1) * 0.5f,
            bounds
        )
        if (!isSplitPairProfile(profile)) return fallback

        val gold = result.points.filter { it.gold }
        if (gold.isEmpty()) return fallback
        val splitX = (bounds.x0 + bounds.x1) * 0.5f
        val left = gold.filter { it.x <= splitX }
        val right = gold.filter { it.x > splitX }
        // Fixed left-first choice prevents a symmetric pair's focus target
        // from hopping between lobes as highlight counts fluctuate.
        val cluster = left.takeIf { it.isNotEmpty() }
            ?: right.takeIf { it.isNotEmpty() }
            ?: return fallback

        fun median(values: List<Float>): Float {
            val sorted = values.sorted()
            val middle = sorted.size / 2
            return if (sorted.size % 2 == 0) {
                (sorted[middle - 1] + sorted[middle]) * 0.5f
            } else sorted[middle]
        }

        val focusX = median(cluster.map { it.x }).coerceIn(0f, 1f)
        val focusY = median(cluster.map { it.y }).coerceIn(0f, 1f)
        val rawX0 = cluster.minOf { it.x }
        val rawY0 = cluster.minOf { it.y }
        val rawX1 = cluster.maxOf { it.x }
        val rawY1 = cluster.maxOf { it.y }
        val halfWidth = maxOf(0.04f, (rawX1 - rawX0) * 0.65f)
        val halfHeight = maxOf(0.04f, (rawY1 - rawY0) * 0.65f)
        return JewelleryFocusTarget(
            focusX,
            focusY,
            MaterialDetector.Bounds(
                (focusX - halfWidth).coerceAtLeast(0f),
                (focusY - halfHeight).coerceAtLeast(0f),
                (focusX + halfWidth).coerceAtMost(1f),
                (focusY + halfHeight).coerceAtMost(1f)
            )
        )
    }

    private fun isSplitPairProfile(profile: CaptureCompositionProfiles.Profile?): Boolean =
        when (profile?.silhouette) {
            CaptureCompositionProfiles.Silhouette.HOOP_PAIR,
            CaptureCompositionProfiles.Silhouette.STUD_PAIR,
            CaptureCompositionProfiles.Silhouette.DROP_PAIR -> true
            else -> false
        }

    /** Relative-distance guidance needs no depth sensor or AI. The apparent
     * ornament area from the deterministic material detector plus the
     * current/maximum optical zoom gives the target distance ratio. Staff
     * move the stand until the centered dashed frame and message turn green. */
    private fun renderStandDistanceGuide(
        guidance: StandDistanceGuide.Guidance?,
        profile: CaptureCompositionProfiles.Profile?
    ) {
        if (phase != Phase.JEWEL || activeCameraSource != ProductionCameraSource.SONY ||
            guidance == null
        ) {
            clearStandDistanceGuide()
            return
        }
        val previous = standDistanceRatioEma
        val smoothed = if (previous == null) guidance.rawDistanceRatio
        else previous + 0.22f * (guidance.rawDistanceRatio - previous)
        standDistanceRatioEma = smoothed
        val direction = StandDistanceGuide.direction(smoothed)
        binding.standGuideText.visibility = View.VISIBLE
        val geometryMessage = StandDistanceGuide.message(guidance, smoothed)
        val profileMessage = profile?.let {
            "${it.label} • ${it.mount.instruction}"
        }
        val opticalLimit = profile?.opticalPlan()?.takeUnless { it.requestedCompositionAchievable }
            ?.let {
                "Kit-lens limit • retain approximately ${it.projectedWidthPixels}×${it.projectedHeightPixels}px for crop"
            }
        binding.standGuideText.text = listOfNotNull(profileMessage, geometryMessage, opticalLimit)
            .joinToString("\n")
        binding.standGuideText.setTextColor(
            ContextCompat.getColor(
                this,
                if (direction == StandDistanceGuide.Direction.READY) R.color.green_ready
                else R.color.amber_working
            )
        )
        if (profile != null) {
            binding.boundsOverlay.updateCompositionGuide(
                profile,
                guidance.targetWidth,
                guidance.targetHeight,
                direction == StandDistanceGuide.Direction.READY
            )
        } else {
            binding.boundsOverlay.updateStandGuide(
                guidance.targetWidth,
                guidance.targetHeight,
                direction == StandDistanceGuide.Direction.READY
            )
        }
    }

    private fun clearStandDistanceGuide() {
        standDistanceRatioEma = null
        binding.standGuideText.visibility = View.GONE
        binding.boundsOverlay.clearStandGuide()
    }

    private data class BarcodeNv21(val bytes: ByteArray, val width: Int, val height: Int)

    /** ML Kit only needs luminance for tag edges. Scale once into reusable
     * 640px storage, then reuse ARGB/NV21 buffers. This keeps tag work off the
     * 25fps stream/UI paths and removes per-scan garbage collection stalls. */
    private fun bitmapToGrayscaleNv21(bitmap: Bitmap): BarcodeNv21 {
        val sourceWidth = bitmap.width
        val sourceHeight = bitmap.height
        val scale = min(1f, SONY_TAG_ANALYSIS_LONG_EDGE.toFloat() / max(sourceWidth, sourceHeight))
        val width = max(2, (sourceWidth * scale).toInt() and -2)
        val height = max(2, (sourceHeight * scale).toInt() and -2)
        val analysisBitmap = if (width == sourceWidth && height == sourceHeight) {
            bitmap
        } else {
            var scaled = barcodeScaledBitmap
            if (scaled == null || scaled.width != width || scaled.height != height) {
                scaled?.recycle()
                scaled = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
                barcodeScaledBitmap = scaled
            }
            Canvas(scaled).drawBitmap(bitmap, null, Rect(0, 0, width, height), barcodeScalePaint)
            scaled
        }
        val frameSize = width * height
        if (barcodeArgbBuffer.size < frameSize) barcodeArgbBuffer = IntArray(frameSize)
        val nv21Size = frameSize + frameSize / 2
        if (barcodeNv21Buffer.size < nv21Size) barcodeNv21Buffer = ByteArray(nv21Size)
        analysisBitmap.getPixels(barcodeArgbBuffer, 0, width, 0, 0, width, height)
        for (i in 0 until frameSize) {
            val pixel = barcodeArgbBuffer[i]
            val red = (pixel shr 16) and 0xff
            val green = (pixel shr 8) and 0xff
            val blue = pixel and 0xff
            barcodeNv21Buffer[i] = ((77 * red + 150 * green + 29 * blue) shr 8).toByte()
        }
        Arrays.fill(barcodeNv21Buffer, frameSize, nv21Size, 128.toByte())
        return BarcodeNv21(barcodeNv21Buffer, width, height)
    }

    /** Checks whether this phone exposes its own computational-photography
     * pipeline (Nothing's "TrueLens engine", HDR/Night/Auto fusion) to
     * third-party CameraX apps via the standard OEM vendor-extensions
     * interface -- the only way that processing is reachable from OUR app
     * at all, since GCam-style ports are standalone APKs, not something a
     * custom app can link against. */
    private fun logExtensionsDiagnostics() {
        val future = androidx.camera.extensions.ExtensionsManager.getInstanceAsync(this, cameraProvider)
        future.addListener({
            try {
                val mgr = future.get()
                val modes = mapOf(
                    "AUTO" to androidx.camera.extensions.ExtensionMode.AUTO,
                    "HDR" to androidx.camera.extensions.ExtensionMode.HDR,
                    "NIGHT" to androidx.camera.extensions.ExtensionMode.NIGHT,
                    "BOKEH" to androidx.camera.extensions.ExtensionMode.BOKEH,
                    "FACE_RETOUCH" to androidx.camera.extensions.ExtensionMode.FACE_RETOUCH,
                )
                for ((name, mode) in modes) {
                    val available = mgr.isExtensionAvailable(CameraSelector.DEFAULT_BACK_CAMERA, mode)
                    Log.i("CameraDiag", "extension $name available=$available")
                }
            } catch (e: Exception) {
                Log.e("CameraDiag", "logExtensionsDiagnostics failed", e)
            }
        }, ContextCompat.getMainExecutor(this))
    }

    /** One-shot dump of every physical lens's focal length / min-focus
     * distance / sensor size, straight from Camera2 -- used to figure out
     * which of this phone's 3 rear lenses is best for close macro work,
     * since CameraSelector.DEFAULT_BACK_CAMERA gives no visibility into
     * that on its own. */
    private fun logCameraDiagnostics() {
        try {
            val mgr = getSystemService(android.hardware.camera2.CameraManager::class.java)
            for (id in mgr.cameraIdList) {
                val ch = mgr.getCameraCharacteristics(id)
                val facing = ch.get(android.hardware.camera2.CameraCharacteristics.LENS_FACING)
                val focal = ch.get(android.hardware.camera2.CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS)
                val minFocusDist = ch.get(android.hardware.camera2.CameraCharacteristics.LENS_INFO_MINIMUM_FOCUS_DISTANCE)
                val sensorSize = ch.get(android.hardware.camera2.CameraCharacteristics.SENSOR_INFO_PHYSICAL_SIZE)
                val pixelArray = ch.get(android.hardware.camera2.CameraCharacteristics.SENSOR_INFO_PIXEL_ARRAY_SIZE)
                val caps = ch.get(android.hardware.camera2.CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES)
                val isLogical = caps?.contains(
                    android.hardware.camera2.CameraMetadata.REQUEST_AVAILABLE_CAPABILITIES_LOGICAL_MULTI_CAMERA
                ) == true
                val physIds = if (isLogical && Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    ch.physicalCameraIds
                } else emptySet()
                // minFocusDistance is in DIOPTERS (1/meters); 0.0 means fixed-focus at infinity,
                // a HIGHER value means it can focus CLOSER (distance_m = 1/diopters).
                val closestFocusCm = if (minFocusDist != null && minFocusDist > 0f) 100f / minFocusDist else null
                Log.i("CameraDiag", "id=$id facing=$facing focalLen=${focal?.joinToString()}mm " +
                    "minFocusDist=${minFocusDist}diopters closestFocus=${closestFocusCm}cm " +
                    "sensor=${sensorSize} pixels=${pixelArray} logical=$isLogical physIds=$physIds")
                for (physId in physIds) {
                    try {
                        val pch = mgr.getCameraCharacteristics(physId)
                        val pFocal = pch.get(android.hardware.camera2.CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS)
                        val pMinFocus = pch.get(android.hardware.camera2.CameraCharacteristics.LENS_INFO_MINIMUM_FOCUS_DISTANCE)
                        val pSensor = pch.get(android.hardware.camera2.CameraCharacteristics.SENSOR_INFO_PHYSICAL_SIZE)
                        val pPixels = pch.get(android.hardware.camera2.CameraCharacteristics.SENSOR_INFO_PIXEL_ARRAY_SIZE)
                        val pClosestCm = if (pMinFocus != null && pMinFocus > 0f) 100f / pMinFocus else null
                        // 2026-08-19, explicit request: check whether this physical
                        // sensor has a higher native resolution hidden behind
                        // binned default output -- common on modern phone sensors
                        // (quad/nona-bayer). ULTRA_HIGH_RESOLUTION_SENSOR (cap 18,
                        // API 33+) plus the MAXIMUM_RESOLUTION stream config map is
                        // the only reliable way to check this; SENSOR_INFO_
                        // PIXEL_ARRAY_SIZE alone only reports the DEFAULT (usually
                        // binned) mode.
                        val pCaps = pch.get(android.hardware.camera2.CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES)
                        val hasUltraHighRes = pCaps?.contains(18) == true  // CAPABILITIES_ULTRA_HIGH_RESOLUTION_SENSOR
                        var maxResSizes = "n/a"
                        if (hasUltraHighRes && android.os.Build.VERSION.SDK_INT >= 33) {
                            val maxMap = pch.get(android.hardware.camera2.CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP_MAXIMUM_RESOLUTION)
                            val sizes = maxMap?.getOutputSizes(android.graphics.ImageFormat.JPEG)
                            maxResSizes = sizes?.sortedByDescending { it.width.toLong() * it.height }
                                ?.take(3)?.joinToString { "${it.width}x${it.height}" } ?: "none"
                        }
                        val defaultMap = pch.get(android.hardware.camera2.CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
                        val defaultJpegSizes = defaultMap?.getOutputSizes(android.graphics.ImageFormat.JPEG)
                            ?.sortedByDescending { it.width.toLong() * it.height }?.take(3)
                            ?.joinToString { "${it.width}x${it.height}" } ?: "none"
                        Log.i("CameraDiag", "  physId=$physId ultraHighRes=$hasUltraHighRes " +
                            "maxResJpegSizes=[$maxResSizes] defaultJpegSizes=[$defaultJpegSizes]")
                        Log.i("CameraDiag", "  physId=$physId focalLen=${pFocal?.joinToString()}mm " +
                            "minFocusDist=${pMinFocus}diopters closestFocus=${pClosestCm}cm " +
                            "sensor=$pSensor pixels=$pPixels")
                    } catch (e: Exception) {
                        Log.w("CameraDiag", "  physId=$physId characteristics failed: ${e.message}")
                    }
                }
            }
        } catch (e: Exception) {
            Log.e("CameraDiag", "logCameraDiagnostics failed", e)
        }
    }

    /** Pins every use case to a specific PHYSICAL sensor inside this
     * phone's logical back multi-camera (2026-08-19, real production
     * finding). logCameraDiagnostics() dumped all 3 physical lenses:
     * physId 4 (5.56mm, closestFocus~10cm, the main/wide sensor) vs physId
     * 3 (12.19mm "telephoto", closestFocus~40cm). Android's own logical-
     * camera zoom handling auto-switches to whichever physical sensor its
     * own heuristic prefers at a given zoomRatio, with NO awareness that
     * this app needs macro focus down to a few cm -- at the zoom levels a
     * small ring/stud needs to fill frame, it was handing off to physId 3,
     * a lens that CANNOT focus that close at all. AF still reports LOCKED
     * (it genuinely locked, just at the nearest distance THAT lens allows),
     * so every existing software focus/sharpness gate passed while the
     * shot was unavoidably soft -- confirmed by comparing directly against
     * the stock Nothing Camera app on the identical ring/lighting/stand,
     * which came out sharp (it's tuned to stay on the macro sensor).
     * Pinning here makes "zoom" a pure digital crop within the ALWAYS-
     * macro-capable sensor instead of a hardware lens swap -- correct
     * regardless of how big the item is or how far/high the gimbal sits,
     * since none of that changes which physical sensor gets used. */
    private fun bindUseCases() {
        bindUseCasesPinned(MACRO_PHYSICAL_CAMERA_ID)
    }

    /** Sony and CameraX were previously left running together. INVISIBLE
     * only hid CameraX's view; its camera, preview surface, analyzer and
     * GPU buffers stayed active. Live measurement: 208 MB graphics and
     * 67% app CPU while Sony itself was delivering healthy fresh frames.
     * Fully unbind the unused phone camera. DSLR mode keeps it unbound even
     * through Sony reconnects; only an explicit mode switch can bind it. */
    private fun suspendPhoneCameraForSony() {
        if (!::cameraProvider.isInitialized) return
        cameraProvider.unbindAll()
        imageCapture = null
        camera = null
        binding.previewView.visibility = View.GONE
        Log.i(TAG, "Phone CameraX suspended while Sony is primary")
    }

    /** physicalCameraId: non-null pins every use case to that physical
     * sensor; null uses the logical multi-camera's own default switching
     * (the pre-2026-08-19 behaviour) -- kept as the fallback path in case
     * this device/CameraX combination rejects the pinned bind, so a
     * rejection degrades to "same as before" rather than a dead camera. */
    private fun bindUseCasesPinned(physicalCameraId: String?) {
        val previewBuilder = Preview.Builder()
        focusZoom.attachCaptureCallback(previewBuilder)
        val analysisBuilder = ImageAnalysis.Builder()
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
        val captureBuilder = ImageCapture.Builder()
            .setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY)
            // Explicit, not relying on CAPTURE_MODE_MAXIMIZE_QUALITY's
            // documented default alone (2026-08-19) -- confirmed via
            // Camera2 characteristics that physId=4's real ceiling is
            // 4096x3072 (12.6MP, no genuine higher-resolution mode exists
            // on this sensor for JPEG output), and the raw capture WAS
            // already landing there. This is insurance against CameraX
            // silently negotiating a lower resolution due to the other
            // simultaneously-bound use cases (Preview/ImageAnalysis), not
            // a fix for a confirmed regression.
            .setResolutionSelector(
                ResolutionSelector.Builder()
                    .setResolutionStrategy(ResolutionStrategy.HIGHEST_AVAILABLE_STRATEGY)
                    .build()
            )
            .setJpegQuality(100)

        if (physicalCameraId != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            androidx.camera.camera2.interop.Camera2Interop.Extender(previewBuilder)
                .setPhysicalCameraId(physicalCameraId)
            androidx.camera.camera2.interop.Camera2Interop.Extender(analysisBuilder)
                .setPhysicalCameraId(physicalCameraId)
            androidx.camera.camera2.interop.Camera2Interop.Extender(captureBuilder)
                .setPhysicalCameraId(physicalCameraId)
        }

        val preview = previewBuilder.build().also {
            it.setSurfaceProvider(binding.previewView.surfaceProvider)
        }
        val analysis = analysisBuilder.build().also {
            it.setAnalyzer(ContextCompat.getMainExecutor(this)) { imageProxy -> onFrame(imageProxy) }
        }
        imageCapture = captureBuilder.build()

        cameraProvider.unbindAll()
        try {
            camera = cameraProvider.bindToLifecycle(
                this, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis, imageCapture
            )
            Log.i("CameraDiag", "bindUseCases physicalCameraId=$physicalCameraId OK")
        } catch (e: Exception) {
            if (physicalCameraId != null) {
                Log.e("CameraDiag", "bindUseCases physicalCameraId=$physicalCameraId REJECTED, falling back to default", e)
                bindUseCasesPinned(null)
                return
            }
            throw e
        }
        camera?.let { focusZoom.bind(it, getSystemService(android.hardware.camera2.CameraManager::class.java)) }
        configureExposureSlider()
    }

    // ---------------------------------------------------------------- Frame analysis

    private fun onFrame(imageProxy: ImageProxy) {
        if (activeCameraSource == ProductionCameraSource.SONY) {
            imageProxy.close()
            return
        }
        if (previewShowing) {
            // The captured-photo preview is up -- don't touch pipeline
            // state or the overlay underneath it at all while it's shown.
            imageProxy.close()
            return
        }
        val now = System.currentTimeMillis()
        if (now - lastAnalysisAt < 150) {
            imageProxy.close()
            return
        }
        lastAnalysisAt = now

        when (phase) {
            Phase.JEWEL -> {
                if (TRACKING_PIPELINE_ACTIVE) {
                    // Synchronous, on the analyzer thread, BEFORE anything
                    // below might touch/close the ImageProxy's underlying
                    // Image -- both the local Mat and the network JPEG need
                    // the buffers to still be valid.
                    runVisionServoFrame(imageProxy, now)
                }
                // Full-frame scan while still hunting (not armed) -- the
                // guide-box restriction is a confirmed blind spot for a
                // corner-positioned object during a search sweep (see
                // MaterialDetector.analyse's fullFrame doc comment). Reverts
                // to the guide-box scan once armed, its original purpose
                // (ignore background clutter at the margins) being the
                // right behaviour again once actually tracking a candidate.
                val result = MaterialDetector.analyse(imageProxy, fullFrame = !armed)
                latestMaterial = result
                latestSharpness = if (result.bounds != null) {
                    SharpnessAnalyzer.score(imageProxy, result.bounds)
                } else 0f

                val rotation = imageProxy.imageInfo.rotationDegrees
                lastMaterialRotationDegrees = rotation
                val boxes = latestObjectBoxesUpright
                // GOLD ONLY, never silver/sparkle -- per explicit request
                // (2026-08-18): the overlay should never light up on
                // anything but actual gold. Previously showed every
                // metal-classified point (gold OR silver OR sparkle-near-
                // metal), which is exactly why a display box's specular
                // highlight or any other bright/desaturated surface could
                // paint dots even though the gold-only tracking logic
                // (bestGoldObjectBox()) was already ignoring it -- the
                // overlay just wasn't telling the truth about what the
                // pipeline actually treats as gold.
                val goldPoints = result.points.filter { it.gold }
                // Once ML Kit has found at least one real object, only trust
                // points that additionally fall inside a genuine detected-
                // object box -- kills stray dots on background/props that
                // happen to pass the colour heuristic but were never a real
                // object boundary. Fails open (shows all gold points) until
                // ML Kit's first detection lands, so the overlay isn't
                // blank on the very first frames. With ML Kit disabled
                // (ML_KIT_OBJECT_DETECTION_ENABLED = false), boxes is
                // always empty, so this always falls open to goldPoints --
                // gold-only filtering is what actually matters now.
                val filteredPoints = if (boxes.isEmpty()) {
                    goldPoints
                } else {
                    goldPoints.filter { p ->
                        val up = uprightPoint(p, rotation)
                        boxes.any { it.contains(up[0], up[1]) }
                    }
                }
                // Focus-peaking style overlay -- screen only, see
                // BoundsOverlayView's own doc comment for why this can
                // never leak into the actual captured photo.
                binding.boundsOverlay.update(filteredPoints, imageProxy.width, imageProxy.height, rotation)

                // ML Kit object detection disabled (2026-08-18) per explicit
                // request: gold colour detection alone, no ML Kit box. It
                // was also the source of the mlOccupancy=null flakiness at
                // small/low zoom sizes -- MaterialDetector's colour/coverage
                // path is now the ONLY source of truth (see
                // bestObjectBox()'s short-circuit and
                // meetsHardCaptureRules()'s colour-based fallback below).
                if (ML_KIT_OBJECT_DETECTION_ENABLED) {
                    val mediaImage = imageProxy.image
                    if (!objectDetectBusy && mediaImage != null) {
                        objectDetectBusy = true
                        val inputImage = InputImage.fromMediaImage(mediaImage, rotation)
                        val uprightW = if (rotation == 90 || rotation == 270) imageProxy.height else imageProxy.width
                        val uprightH = if (rotation == 90 || rotation == 270) imageProxy.width else imageProxy.height
                        objectDetector.process(inputImage)
                            .addOnSuccessListener { objects ->
                                latestObjectBoxesUpright = objects.map { obj ->
                                    val r = obj.boundingBox
                                    RectF(
                                        r.left / uprightW.toFloat(), r.top / uprightH.toFloat(),
                                        r.right / uprightW.toFloat(), r.bottom / uprightH.toFloat()
                                    )
                                }
                            }
                            .addOnFailureListener { e -> Log.e(TAG, "Object detection failed", e) }
                            .addOnCompleteListener {
                                objectDetectBusy = false
                                imageProxy.close()
                            }
                    } else {
                        imageProxy.close()
                    }
                } else {
                    imageProxy.close()
                }
            }
            Phase.TAG -> {
                binding.boundsOverlay.update(emptyList(), 0, 0, 0)
                if (barcodeBusy) {
                    imageProxy.close()
                    return
                }
                val mediaImage = imageProxy.image
                if (mediaImage == null) {
                    imageProxy.close()
                    return
                }
                barcodeBusy = true
                barcodeAttempts += 1
                val inputImage = InputImage.fromMediaImage(mediaImage, imageProxy.imageInfo.rotationDegrees)
                barcodeScanner.process(inputImage)
                    .addOnSuccessListener { barcodes ->
                        lastBarcodeCount = barcodes.size
                        val code = barcodes.firstOrNull { !it.rawValue.isNullOrBlank() }?.rawValue
                        recordTagCode(code)
                    }
                    .addOnFailureListener { e ->
                        // Silently swallowed before this: an ML Kit failure
                        // (e.g. its scanner module not yet downloaded/ready
                        // on this device) meant onSuccessListener simply
                        // never fired, tagCodeHistory never advanced, and
                        // the status text sat on "Scanning tag..." forever
                        // with nothing in logcat pointing at why.
                        Log.e(TAG, "Barcode scan failed", e)
                        lastBarcodeError = e.message ?: e.javaClass.simpleName
                    }
                    .addOnCompleteListener {
                        barcodeBusy = false
                        imageProxy.close()
                    }
            }
            Phase.UPLOADING -> imageProxy.close()
        }
    }

    // ---------------------------------------------------------------- Vision servo pipeline (DINO + MIL)
    //
    // Orchestration only -- VisionServoController owns all state/servo
    // decisions, JewelleryTracker owns MIL+Kalman, DetectorClient owns the
    // WebSocket, FrameConversion owns pixel-format plumbing. MainActivity's
    // job is: feed frames in, feed DINO results in, execute the ServoCommand
    // that comes back via applyServoCommand() -- the ONE function in this
    // class allowed to call rsc2.moveOut/focusZoom for this pipeline.
    //
    // shutterEnabled stays false for the physical checkpoint: reaching
    // LOCKED only logs "CAPTURE WOULD FIRE", nothing here ever calls
    // captureJewel(). Do not wire that until the checkpoint has passed.

    private fun connectDetector() {
        if (!DINO_SERVO_ENABLED) {
            Log.i("VisionServo", "Local-AI detector disabled; deterministic gold detector active")
            return
        }
        val serverUrl = serverUrl()
        val host = try { java.net.URI(serverUrl).host } catch (e: Exception) { null }
        if (host.isNullOrBlank()) return
        val wsUrl = "ws://$host:8765"
        val client = DetectorClient { result -> handler.post { onDinoResult(result) } }
        client.connect(wsUrl)
        detectorClient = client
        Log.i("VisionServo", "[DINO] connecting to $wsUrl")
    }

    private fun onDinoResult(result: DetectorClient.DetectionResult) {
        if (!result.detected) return
        val sensorBox = RectF(result.x, result.y, result.x + result.w, result.y + result.h)
        val upright = FrameConversion.uprightBox(sensorBox, cachedRotationDegrees)
        visionServo.onDinoDetection(
            result.frameId, result.ageMs(),
            NormalizedBox(upright.left, upright.top, upright.right, upright.bottom)
        )
    }

    private fun runVisionServoFrame(imageProxy: ImageProxy, nowMs: Long) {
        cachedRotationDegrees = imageProxy.imageInfo.rotationDegrees

        val gray = FrameConversion.imageProxyToGrayMat(imageProxy)
        val upright = FrameConversion.rotateMatUpright(gray, cachedRotationDegrees)
        val cmd = try {
            visionServo.onCameraFrame(upright, nowMs)
        } finally {
            if (upright !== gray) upright.release()
            gray.release()
        }

        if (cmd != null) applyServoCommand(cmd)

        val client = detectorClient
        if (client != null && client.isConnected && nowMs - lastDetectorSendAt >= DETECTOR_SEND_INTERVAL_MS) {
            val jpeg = FrameConversion.imageProxyToJpegColor(imageProxy, DETECTOR_FRAME_LONG_EDGE, DETECTOR_JPEG_QUALITY)
            if (client.sendFrame(jpeg) >= 0) lastDetectorSendAt = nowMs
        }
    }

    /** The single funnel for every pan/tilt/zoom command this pipeline
     * issues. Pan and tilt are fired as alternating single-axis bursts,
     * never combined in one BLE frame -- combining tilt+pan in a single
     * DUML frame caused an immediate, unrecoverable RSC2 disconnect the one
     * time it was tried (see RSC2Controller's own doc comment); alternating
     * fast small proportional nudges is the closest safe approximation of
     * "simultaneous" this hardware allows. */
    private fun applyServoCommand(cmd: VisionServoController.ServoCommand) {
        if (!rsc2.isReady) return
        updateCameraTrackingRegion(cmd.targetCx, cmd.targetCy)

        val nowMs = System.currentTimeMillis()
        if (nowMs - lastServoAt >= SERVO_INTERVAL_MS && (cmd.pan != 0f || cmd.tilt != 0f)) {
            lastServoAt = nowMs
            val choosePan = if (cmd.pan != 0f && cmd.tilt != 0f) {
                lastServoAxisWasPan = !lastServoAxisWasPan
                lastServoAxisWasPan
            } else cmd.pan != 0f
            if (choosePan) {
                val mag = abs(cmd.pan)
                val durMs = (SERVO_MIN_MS + mag * (SERVO_MAX_MS - SERVO_MIN_MS)).toLong()
                val deflection = (mag * SERVO_MAX_DEFLECTION).toInt()
                val axis = DumlProtocol.AXIS_CENTER + (if (cmd.pan > 0) deflection else -deflection)
                rsc2.moveOut(axis3 = axis, durationMs = durMs, settleMs = 0L) {}
            } else {
                val mag = abs(cmd.tilt)
                val durMs = (SERVO_MIN_MS + mag * (SERVO_MAX_MS - SERVO_MIN_MS)).toLong()
                val deflection = (mag * SERVO_MAX_DEFLECTION).toInt()
                // Positive tilt error (ey<0 handled inside VisionServoController)
                // maps the same direction sense as the existing centering code.
                val axis = DumlProtocol.AXIS_CENTER + (if (cmd.tilt > 0) deflection else -deflection)
                rsc2.moveOut(axis1 = axis, durationMs = durMs, settleMs = 0L) {}
            }
        }

        if (nowMs - lastZoomServoAt >= ZOOM_SERVO_INTERVAL_MS && cmd.zoomStep != 0f) {
            lastZoomServoAt = nowMs
            val zoom = cameraZoomRatio()
            val range = cameraZoomRange()
            val next = (zoom * (1f + cmd.zoomStep)).coerceIn(range.start, min(range.endInclusive, MAX_LIVE_ZOOM_RATIO))
            setCameraZoomRatio(next)
        }
    }

    private fun recordTagCode(code: String?) {
        // A locked tag remains latched until resetForNewItem(TAG). Empty
        // frames during preview/camera transitions must not erase it.
        if (stableTagCode != null) return
        if (code == null) return
        val trimmed = code.trim()
        if (trimmed.isEmpty()) return
        // Do not hammer the server every analysis frame for the same known-
        // bad decode. A different decoded value immediately releases it.
        if (trimmed == invalidTagCode) return
        invalidTagCode = null
        // A strict stock-label-shaped decode can go directly to the
        // authoritative catalogue lookup. Requiring it twice made a real
        // label wait for a second rare glare-free frame. Non-standard values
        // still require two matching positive frames.
        tagCodeHistory = (tagCodeHistory + trimmed).takeLast(4).toMutableList()
        stableTagCode = if (
            TAG_CODE_PATTERN.matches(trimmed) || tagCodeHistory.count { it == trimmed } >= 2
        ) trimmed else null
        if (stableTagCode != null) {
            resolveCategoryForCurrentTag()
        }
    }

    /** Resolve before capture. Unknown labels are rejected here, before the
     * operator spends a full three-angle Sony cycle. Transport failures keep
     * the decoded label latched and retry without misclassifying it. */
    private fun resolveCategoryForCurrentTag() {
        val code = stableTagCode ?: return
        if (categoryResolutionCode == code) return
        resolvedCategoryKey = null
        categoryResolutionError = null
        categoryResolutionCode = code
        lifecycleScope.launch {
            val result = UploadClient.resolveCategory(serverUrl(), code)
            if (stableTagCode != code) {
                if (categoryResolutionCode == code) categoryResolutionCode = null
                return@launch
            }
            categoryResolutionCode = null
            val category = result.category
            if (category != null) {
                resolvedCategoryKey = category.key
                categoryResolutionError = null
                logCaptureEvent("tag_category_resolved", mapOf("code" to code, "category" to category.key))
                fetchStudFlagForCurrentTag(code)
                return@launch
            }
            resolvedCategoryKey = null
            categoryResolutionError = result.error
            if (result.serverReached) {
                invalidTagCode = code
                stableTagCode = null
                confirmedTagEvidenceJpeg = null
                tagCodeHistory = mutableListOf()
                autoFired = false
                logCaptureEvent("tag_rejected_unknown_category", mapOf("code" to code, "error" to result.error))
                setStatus("Unknown stock label $code — show the correct label", ready = false)
                Toast.makeText(this@MainActivity, "Unknown stock label: $code", Toast.LENGTH_LONG).show()
            } else {
                logCaptureEvent("tag_category_server_unreachable", mapOf("code" to code, "error" to result.error))
                setStatus("Catalogue server unavailable — retrying…", ready = false)
                triggerServerRediscovery()
                handler.postDelayed({
                    if (phase == Phase.TAG && stableTagCode == code && categoryResolutionCode == null) {
                        resolveCategoryForCurrentTag()
                    }
                }, 1000L)
            }
        }
    }

    @Volatile private var serverRediscoveryInFlight = false

    /** Hardwall for capture_server.py's own laptop IP drifting on this same
     * LAN (2026-08-28) -- confirmed live the day this was added: the
     * laptop moved off both addresses UploadClient's DNS fallback had
     * hardcoded, and mDNS alone left the operator stuck on "Checking tag
     * category..." with no visible recovery. Mirrors SonyCameraDiscovery's
     * approach for the camera: sweep the tablet's own current subnet for
     * a host that answers as capture_server.py, cache it for immediate
     * reuse (UploadClient.discoveredServerIp) and persist it so the NEXT
     * launch starts from the last-known-good address too. */
    private fun triggerServerRediscovery() {
        if (serverRediscoveryInFlight) return
        serverRediscoveryInFlight = true
        Thread({
            try {
                val port = try {
                    java.net.URI(serverUrl()).port.takeIf { it > 0 } ?: 7660
                } catch (_: Exception) {
                    7660
                }
                val preferred = prefs.getString("capture_server_ip", null)
                val found = ServerDiscovery.discoverServerIp(applicationContext, port, preferred)
                if (found != null && found != UploadClient.discoveredServerIp) {
                    Log.i(TAG, "capture_server.py rediscovered at $found")
                    UploadClient.discoveredServerIp = found
                    prefs.edit().putString("capture_server_ip", found).apply()
                    handler.post {
                        if (!isDestroyed && phase == Phase.TAG && stableTagCode != null &&
                            categoryResolutionCode == null && resolvedCategoryKey == null
                        ) {
                            resolveCategoryForCurrentTag()
                        }
                    }
                }
            } catch (e: Exception) {
                Log.w(TAG, "capture_server.py rediscovery failed: ${e.message}", e)
            } finally {
                serverRediscoveryInFlight = false
            }
        }, "ServerRediscovery").start()
    }

    /** Fire-and-forget stud-flag lookup, same pattern/reasoning as category
     * resolution just above -- fetched fresh per tag so a correction made
     * on a PREVIOUS item for this same tag code (recapture after delete)
     * is picked back up, not silently reset to "unknown". */
    private fun fetchStudFlagForCurrentTag(code: String) {
        studFlagFetchInFlight = true
        lifecycleScope.launch {
            val result = try {
                UploadClient.getStudFlag(serverUrl(), code)
            } catch (e: Exception) {
                null
            }
            if (stableTagCode == code) {
                studFlagPersisted = result
            }
            studFlagFetchInFlight = false
        }
    }

    /** Tap handler for studStatusText -- flips whichever value is
     * currently displayed and persists it immediately. Optimistic UI
     * (updates studFlagPersisted before the network call resolves) since
     * this is a deliberate, explicit staff action, not a background guess
     * -- reverted only if the save actually fails, logged so a silent
     * network failure doesn't leave staff believing a correction stuck
     * when it didn't. */
    private fun onStudStatusTapped() {
        val code = stableTagCode ?: return
        val current = studFlagPersisted ?: studAutoGuess
        val next = !current
        studFlagPersisted = next
        updateStudStatusUi()
        lifecycleScope.launch {
            val staffName = prefs.getString("staff_name", "") ?: ""
            val saved = try {
                UploadClient.setStudFlag(serverUrl(), code, next, staffName)
            } catch (e: Exception) {
                null
            }
            if (saved == null) {
                Log.w(TAG, "onStudStatusTapped: save failed for tag=$code hasStud=$next")
                Toast.makeText(this@MainActivity, "Stud correction didn't save — check connection", Toast.LENGTH_LONG).show()
            } else if (stableTagCode == code) {
                studFlagPersisted = saved
                updateStudStatusUi()
            }
        }
    }

    /** Shows/updates the stud status card. "(guess)" vs no suffix
     * distinguishes an unconfirmed on-device heuristic from an actual
     * persisted/confirmed value -- staff should be able to tell at a
     * glance whether this needs their attention. Hidden entirely outside
     * JEWEL phase or before a tag has resolved, since there's nothing
     * meaningful to show yet. */
    private fun updateStudStatusUi() {
        val card = binding.studStatusText
        if (phase != Phase.JEWEL || stableTagCode == null) {
            card.visibility = View.GONE
            return
        }
        card.visibility = View.VISIBLE
        val persisted = studFlagPersisted
        val shown = persisted ?: studAutoGuess
        val suffix = if (persisted == null) " (guess — tap to correct)" else " (tap to correct)"
        card.text = if (shown) "Stud: Yes$suffix" else "Stud: No$suffix"
        card.setOnClickListener { onStudStatusTapped() }
    }

    // ---------------------------------------------------------------- Pipeline tick

    private val tickRunnable = object : Runnable {
        override fun run() {
            updateGimbalStatusBadge()
            if (activeCameraSource == ProductionCameraSource.SONY &&
                ::sonyProduction.isInitialized && !sonyProduction.isAvailable &&
                phase != Phase.UPLOADING
            ) {
                setStatus("Sony camera restoring…", ready = false)
                handler.postDelayed(this, TICK_INTERVAL_MS)
                return
            }
            when (phase) {
                Phase.JEWEL -> tickJewel()
                Phase.TAG -> tickTag()
                Phase.UPLOADING -> {}
            }
            handler.postDelayed(this, TICK_INTERVAL_MS)
        }
    }

    /** On-screen "is the gimbal actually connected right now" indicator --
     * previously the only way to know was watching logcat for "RSC 2
     * ready"/"disconnected" lines, not something staff can check. Updated
     * every tick so it reflects reality within ~150ms of a real
     * connect/disconnect, including mid-move ("Moving…") so a stuck
     * gimbal doesn't read as falsely idle-connected. */
    private fun updateGimbalStatusBadge() {
        val (text, color) = when {
            !rsc2.isReady -> "Gimbal: not connected" to 0xDD7F1D1D.toInt()
            rsc2.isMoving -> "Gimbal: moving" to 0xDD92600A.toInt()
            else -> "Gimbal: connected" to 0xDD15803D.toInt()
        }
        binding.gimbalStatusText.text = text
        binding.gimbalStatusText.background = pillDrawable(color)
    }

    /** Rounded, card-style pill background built at runtime -- used
     * anywhere a status badge needs a state colour (gimbal connected/
     * moving/not-connected, status-ready) without falling back to the
     * old flat rectangle setBackgroundColor() gave, which clobbered the
     * rounded @drawable/bg_card look applied in the layout XML. */
    private fun pillDrawable(color: Int): android.graphics.drawable.GradientDrawable =
        android.graphics.drawable.GradientDrawable().apply {
            setColor(color)
            cornerRadius = 12f * resources.displayMetrics.density
        }

    private fun tickTag() {
        if (previewShowing) return
        if (SKIP_BARCODE_FOR_TESTING && !autoFired) {
            // Skip the barcode scan entirely while testing the JEWEL flow
            // -- no tag needed in frame at all. Still captures a real
            // (placeholder) tagJpeg since uploadPair()/uploadMulti() both
            // fail closed ("Missing photo") on a null tag photo. Set
            // SKIP_BARCODE_FOR_TESTING back to false for real use.
            autoFired = true
            stableTagCode = "TEST-${System.currentTimeMillis()}"
            captureTagFrame { bytes ->
                tagJpeg = bytes
                resetForNewItem(Phase.JEWEL)
                promptToPlaceMainItem()
            }
            return
        }
        val validated = stableTagCode != null && resolvedCategoryKey != null
        binding.tagCodeText.text = when {
            validated -> "Tag: $stableTagCode · ${resolvedCategoryKey} · ready"
            stableTagCode != null -> "Tag: $stableTagCode · checking catalogue…"
            invalidTagCode != null -> "Unknown label: $invalidTagCode · show another label"
            else -> "Show the tag QR/barcode…"
        }
        setStatus(
            when {
                validated -> "Tag validated. Capturing…"
                stableTagCode != null -> "Checking tag category…"
                tagBurstActive -> "Confirming label $tagBurstProgress/$SONY_TAG_BURST_FRAMES…"
                invalidTagCode != null -> "Unknown stock label — show the correct label"
                else -> "Scanning tag…"
            },
            ready = validated
        )
        binding.debugText.text = "attempts=$barcodeAttempts  lastSeen=$lastBarcodeCount" +
            (if (tagBurstActive) "  burst=$tagBurstProgress/$SONY_TAG_BURST_FRAMES" else "") +
            (lastBarcodeError?.let { "  error=$it" } ?: "")
        if (validated && !autoFired) {
            autoFired = true
            captureTagFrame { bytes ->
                if (bytes == null) {
                    autoFired = false
                    setStatus("Tag capture failed — retrying", ready = false)
                    return@captureTagFrame
                }
                tagJpeg = bytes
                // The catalogue already validated the decoded tag. A forced
                // two-second image-review countdown only held production and
                // looked like failed detection. Preserve evidence, then move
                // immediately to ornament placement.
                resetForNewItem(Phase.JEWEL)
                promptToPlaceMainItem()
            }
        }
    }

    /** A Sony Live View frame is sufficient for the label record and avoids
     * disrupting the stream with a full-resolution shutter cycle. Jewellery
     * photos still use [captureFullRes]. */
    private fun captureTagFrame(onResult: (ByteArray?) -> Unit) {
        if (activeCameraSource != ProductionCameraSource.SONY) {
            captureFullRes(onResult = onResult)
            return
        }
        onResult(confirmedTagEvidenceJpeg?.copyOf() ?: sonyProduction.currentLiveViewJpeg())
    }

    /**
     * Mirrors capture.html's advanceCapturePipeline: verify the CURRENT
     * zoom is genuinely clean (real AF state + sharpness cross-check)
     * before EVER advancing zoom, and stop the instant everything is green
     * together rather than chasing a fixed coverage target. See that
     * function's comments for the full reasoning -- same lessons, applied
     * here with a stronger focus signal.
     */
    private fun tickJewel() {
        if (previewShowing || isZooming || inAngleSequence || jewelReadyPending) return
        // Manual override (2026-08-18): staff is flying pan/tilt/zoom/focus/
        // exposure by hand via the on-screen manual controls -- auto mode
        // must not issue any competing gimbal/zoom/exposure/capture command
        // while that's true. Continuous AF/preview keep running (this only
        // gates tickJewel, not the camera pipeline itself); resumeAutoButton
        // is the only way back to auto.
        if (manualModeActive) {
            setStatus("Manual mode — auto standing by", ready = false)
            return
        }
        val now = System.currentTimeMillis()
        val result = latestMaterial
        if (result != null) {
            studAutoGuess = MaterialDetector.studCandidate(result.points)
        }
        updateStudStatusUi()

        if (TRACKING_PIPELINE_ACTIVE) {
            // VisionServoController is fully in charge of centering/framing/
            // zoom once it has a target -- the legacy arm/zoom-climb/capture
            // logic below must not run at all while it's active, so it can
            // never fire a shutter during the physical checkpoint (capture
            // stays hard-disabled pipeline-wide: VisionServoController.
            // shutterEnabled is false and nothing here ever calls it anyway).
            // The legacy deterministic hunt sweep is kept as the SEARCHING-
            // only fallback search behaviour, and becomes fully subordinate
            // to vision servo the instant a target is found -- it must not
            // move the gimbal once tracking has started.
            if (visionServo.state == VisionState.SEARCHING) {
                if (AUTONOMOUS_BLIND_HUNT_ENABLED && !detectedNow() &&
                    rsc2.isReady && now >= huntCooldownUntil
                ) {
                    if (huntStartedAt == 0L) huntStartedAt = now
                    if (now - huntStartedAt > HUNT_GRACE_MS) huntStep()
                }
                setStatus("Searching (DINO+MIL checkpoint)…", ready = false)
            } else {
                huntStartedAt = 0L
                setStatus("Tracking (checkpoint -- capture disabled): ${visionServo.state}", ready = false)
            }
            return
        }

        if (!armed) {
            // Hybrid arm gate: MaterialDetector's colour heuristic OR ML
            // Kit's real object box, so a silver piece (weak/no colour
            // signal) still arms the pipeline, not just gold.
            if (!detectedNow()) {
                if (AUTONOMOUS_BLIND_HUNT_ENABLED && rsc2.isReady &&
                    now >= huntCooldownUntil
                ) {
                    if (huntStartedAt == 0L) huntStartedAt = now
                    if (now - huntStartedAt > HUNT_GRACE_MS) {
                        huntStep()
                        return
                    }
                } else {
                    huntStartedAt = 0L
                }
                setStatus("Waiting for a verified ornament target…", ready = false)
                return
            }
            huntStartedAt = 0L
            armed = true
            armedAt = now
            // Continuous AF becomes the baseline the instant something's
            // detected -- not a one-shot trigger. Region tracking below
            // keeps steering it at the object every tick from here on; the
            // zoom-climb logic further down still does its own decisive
            // triggerAutoFocus() calls when it needs a definitive lock,
            // which is fine layered on top (triggerAutoFocus always
            // explicitly sets AF_MODE=AUTO regardless of what continuous
            // tracking set it to).
            startCameraContinuousTracking()
        }

        // Skip once a definitive triggerAutoFocus() lock is in flight for
        // this zoom level. Root cause found live (2026-08-18): CameraX's
        // Camera2CameraControl.setCaptureRequestOptions() REPLACES the
        // entire interop option set on every call, it does not merge --
        // updateTrackingRegionFor()'s call only sets AF_REGIONS/AE_REGIONS,
        // so calling it every tick (as before) silently wiped out
        // CONTROL_AF_MODE_AUTO + CONTROL_AF_TRIGGER_START the very next
        // tick after triggerAutoFocus() set them, before Camera2 could
        // ever report FOCUSED_LOCKED. That's what "stuck at max zoom,
        // status stuck on Focusing…, af never leaves passive-focused,
        // never captures" actually was -- the pipeline was re-cancelling
        // its own focus lock every ~150ms, forever.
        if (!focusTriggeredThisLevel) {
            updateTrackingRegionFor(result)
        }

        // THIRD pass on this same struggle (2026-08-18): the real bug was
        // structural, not tuning. MaterialDetector.analyse() computes
        // result.bounds whenever ANY warm/metal pixel was found at all
        // (warm > 0) -- material=true is a STRICTER, separate threshold on
        // top of that (coverage/ratio must additionally clear
        // MIN_LIVE_COVERAGE-scale floors). But this branch was gating on
        // material alone, so every time that stricter flag flickered false
        // -- confirmed live swinging 0.006-0.15 tick to tick on a
        // genuinely stationary piece -- centering was skipped entirely
        // (this whole function returns early here), not just the zoom
        // climb. That's what "gimbal not moving, stuck on Re-centre the
        // item" actually was: bounds/mlBox were very likely still valid
        // most of those ticks, but nothing downstream ever got to look at
        // them. Only treat it as truly lost when NEITHER a gold ML box NOR
        // MaterialDetector's own bounds exist -- that's the actual "no
        // position estimate at all" case, not "coverage momentarily read
        // low."
        if (result == null || (bestObjectBox() == null && !isTrustedMaterialTarget(result))) {
            // Lost the piece -- likely walked out of frame on a zoom step
            // (digital/hybrid zoom on this class of lens is still centre-
            // anchored). Ease back to re-acquire rather than climbing
            // further on an empty frame. Same grace-tick + zoom-floor
            // debounce as before (see MATERIAL_LOSS_GRACE_TICKS/
            // ZOOM_BACKOFF_MIN_ZOOM doc comments) -- kept because a true
            // zero-detection tick can still be a one-off glitch.
            materialLossStreak += 1
            if (materialLossStreak < MATERIAL_LOSS_GRACE_TICKS) {
                setStatus("Tracking ornament — reacquiring…", ready = false)
                return
            }
            // A real target that disappears immediately after our last
            // gimbal nudge was probably pushed out of frame. Let the existing
            // exact-duration revert path undo that move; tiny warm fragments
            // are deliberately treated as lost here too.
            if (result != null && rsc2.isReady) {
                attemptCenteringCorrection(result)
            }
            val zoom = cameraZoomRatio()
            if (zoom > ZOOM_BACKOFF_MIN_ZOOM) {
                smoothZoomTo((zoom * ZOOM_BACKOFF_RATIO).coerceAtLeast(1f))
                stepFocusAttempts = 0
                focusTriggeredThisLevel = false
            }
            setStatus("Tracking ornament — reacquiring…", ready = false)
            return
        }
        materialLossStreak = 0

        // Concurrent centering, not deferred to the end -- per explicit
        // request (2026-08-18): before this, attemptCenteringCorrection()
        // was only ever called inside the final "ready" branch below, once
        // coverage/focus/zoom were ALL already satisfied. That made
        // centering and zooming two sequential PHASES (climb zoom fully
        // first, only then start correcting position) instead of
        // happening together -- exactly the "I see zoom happening then
        // gimbal moving" behaviour reported live. Gimbal BLE commands and
        // digital zoom are independent hardware paths with no reason to
        // serialize; firing a centering correction every tick regardless
        // of zoom-climb phase lets both run concurrently.
        //
        // Production hardwall: never replace the bounded correction budget
        // with Int.MAX_VALUE here. Live LR22/18 testing (2026-08-25) proved
        // that a flickering target could otherwise enter an endless
        // nudge/lost/revert loop (182+ actions) and physically hunt for
        // minutes. Four actions are enough to establish convergence. If
        // they do not converge, stop moving; the operator can reposition
        // the piece or explicitly enter manual mode with zoom +/-.
        if (rsc2.isReady) attemptCenteringCorrection(result)

        val zoom = cameraZoomRatio()
        val zoomRange = cameraZoomRange()
        val effectiveZoomCeiling = min(
            min(zoomRange.endInclusive, MAX_LIVE_ZOOM_RATIO),
            maxUsableZoom
        )
        val atZoomCeiling = zoom >= effectiveZoomCeiling - 0.02f
        // Long items pin near the WIDEST zoom instead of climbing
        // (2026-08-28, explicit request): a NECK_CURVE piece (chain/mala/
        // necklace) genuinely needs close to max zoom-out just to fit
        // end-to-end -- the dynamic coverage climb kept fighting the
        // follow-gold zoom-out rule over it (climb pushes in chasing 75%
        // area, follow-gold pulls back out once that growth reads as
        // off-center/edge-clipped), a real live-confirmed oscillation loop
        // that never settled. Skipping the climb for these categories
        // entirely removes the fight instead of trying to tune it away.
        val isLongItemCategory = CaptureCompositionProfiles.forCategory(resolvedCategoryKey)
            ?.silhouette == CaptureCompositionProfiles.Silhouette.NECK_CURVE
        val atZoomFloor = zoom <= zoomRange.start + 0.05f
        // At the ceiling, accept whatever coverage is on offer as "the best
        // framing available" -- but this must NOT mean skipping focus
        // verification. It previously called captureJewel() directly here,
        // which is exactly how a shot could come out both too-far-away AND
        // blurry at once: an item too small to ever cross MIN_LIVE_COVERAGE
        // within the zoom cap got captured with focus never even checked.
        // Folding the ceiling into coverageOk instead just changes what
        // "enough of the frame" means for THIS item; every capture still
        // goes through the same focusLocked + sharpEnough gate below.
        // The climb target IS the non-negotiable occupancy rule now, not
        // MaterialDetector's capped colour coverage -- that metric is
        // measured within a 64%x68% guide region and mathematically caps
        // out around 0.435, so climbing only to MIN_LIVE_COVERAGE(0.24)
        // stopped WAY short of the real CAPTURE_MIN_OCCUPANCY(0.75)
        // requirement, and meetsHardCaptureRules() would then refuse to
        // capture forever. ML Kit's box is full-frame-normalized with no
        // such cap, so it's what the climb targets once it's available;
        // falls back to the softer colour metric only before ML Kit's
        // first detection lands (something to climb toward, not nothing).
        val mlBoxForCoverage = bestObjectBox()
        val mlOccupancy = mlBoxForCoverage?.let { it.width() * it.height() }
        // With ML Kit disabled, mlOccupancy is always null, so this used to
        // permanently fall back to result.coverage >= MIN_LIVE_COVERAGE
        // (0.24) -- exactly the gap this function's own doc comment
        // predicted: that capped colour metric maxes out around 0.435 and
        // was never meant to be the real climb target, CAPTURE_MIN_
        // OCCUPANCY (0.75) was. Confirmed live (2026-08-18): af=LOCKED,
        // sharp=100, a genuinely good shot, coverage=0.088 -- coverageOk
        // read true only via atZoomCeiling, then meetsHardCaptureRules()
        // (which correctly uses bounds.area(), uncapped) failed on real
        // occupancy every single tick with no path back into the zoom
        // climb, forever. Use the same bounds-based, full-frame-normalized
        // occupancy meetsHardCaptureRules() checks, not the capped colour
        // metric, so climb target and final gate agree on what "big
        // enough" means.
        val colourOccupancy = result.bounds?.area() ?: result.coverage
        val coverageOk = (if (mlOccupancy != null) mlOccupancy >= CAPTURE_MIN_OCCUPANCY
                          else colourOccupancy >= CAPTURE_MIN_OCCUPANCY) || atZoomCeiling ||
            (isLongItemCategory && atZoomFloor)
        // Sony exposes one serialized PTP control lane. Exposure used to run
        // before this framing decision and repeatedly occupied that lane,
        // causing every concurrent zoom request to fail busy while the UI
        // said "Zooming in" forever at 1.0x. Frame first; exposure correction
        // starts once coverage is sufficient and no zoom command is needed.
        if (coverageOk) applyAutoExposure(result)
        val b = result.bounds
        // Long items (chains/malas/bracelets on TOP_RAIL/LOWER_RAIL) can run
        // past the top/bottom frame edge at the current stand distance/zoom
        // without ever failing coverageOk -- the visible slice is still
        // "enough of the frame". The angle-capture wait loop already checks
        // this (waitForStableFrame); tickJewel never did (2026-08-28 fix).
        // Without it, a clipped long item fell straight through to the
        // wrongShape check below, since a truncated box's aspect ratio no
        // longer matches the category's full-length shape -- giving the
        // misleading "Reposition -- tracking looks off" instead of the
        // accurate, actionable message that matches what the on-screen
        // StandDistanceGuide banner is already telling the operator.
        val edgeClipped = MaterialDetector.touchesFrameEdge(b)
        // UNIVERSAL FOLLOW-THE-GOLD RULE (2026-08-28, explicit top-priority
        // request): wherever gold is visible in the frame -- top, bottom,
        // left, right, doesn't matter -- getting the gimbal onto it takes
        // precedence over every other framing decision below, and if it's
        // badly off-center or already touching an edge, the correct first
        // move is to zoom OUT (buy room to work with) rather than continue
        // climbing zoom IN toward it. Checked before wrongShape, coverage,
        // and the zoom-in climb -- none of those get a turn until this is
        // satisfied. Centering itself already ran this same tick
        // (attemptCenteringCorrection, above); this only decides whether
        // zoom should retreat to give that correction room, instead of the
        // climb below fighting it by pushing zoom in on a still-uncentered
        // target.
        //
        // NOT gated on coverageOk (live-confirmed on a long mala/chain): the
        // zoom-in climb below only stops once AREA occupancy crosses
        // CAPTURE_MIN_OCCUPANCY, with no awareness of the box already
        // touching an edge. A long thin item's clipped area can still read
        // well under that threshold, so gating this on coverageOk let the
        // climb keep zooming PAST the point of clipping, chasing an area
        // target this item's own aspect ratio could never reach without
        // running off the top/bottom first. Checking edgeClipped here,
        // before the climb block below, stops the zoom-in the moment
        // clipping starts -- matching what StandDistanceGuide's "MOVE
        // STAND FARTHER" banner is already telling the operator, instead of
        // the climb fighting that guidance every tick.
        if (b != null) {
            val gx = (b.x0 + b.x1) / 2f
            val gy = (b.y0 + b.y1) / 2f
            val goldOffCenter = max(abs(gx - 0.5f), abs(gy - 0.5f))
            if ((edgeClipped || goldOffCenter > FOLLOW_GOLD_ZOOM_OUT_DEADBAND) &&
                zoom > zoomRange.start + 0.05f &&
                now - lastZoomChangeAt >= ZOOM_STEP_INTERVAL_MS
            ) {
                val next = (zoom / ZOOM_STEP_RATIO).coerceAtLeast(zoomRange.start)
                if (next < zoom - 0.01f) {
                    Log.i(TAG, "followGold zoomOut offCenter=$goldOffCenter edgeClipped=$edgeClipped zoom=$zoom->$next")
                    smoothZoomTo(next)
                    setStatus("Recentering…", ready = false)
                    return
                }
            }
        }
        val zoomSettled = now - lastZoomChangeAt >= ZOOM_SETTLE_MS
        val afState = cameraAfState()
        val focusLocked = isCameraFocusLocked(afState)
        val focusFailed = isCameraFocusFailed(afState)
        val sharpEnough = latestSharpness >= SHARPNESS_THRESHOLD
        // Standing rule: no blown-out white on the gold at all -- any
        // clipped highlight there is already-lost design detail (engraving,
        // texture) that no post-processing gets back. applyAutoExposure()
        // above steps EV down toward fixing this, but it was only ever a
        // continuous background corrector -- nothing stopped the shutter
        // from firing mid-correction, before the step-down had actually
        // brought the highlight under control. Confirmed live (2026-08-19,
        // GR22/127): captured with a visibly blown highlight straight
        // across the ring's engraved face despite the corrector running.
        // Gating capture on this (not just adjusting exposure and hoping)
        // closes that gap.
        val goldOverexposed = result.highlightClipFraction > 0f
        // Explicit phase label for diagnostics, in the spirit of the DINO/
        // MIL branch's VisionState enum (2026-08-18 port) -- derived
        // read-only from signals already computed above, no new EMA-
        // mutating calls, so it can't change any actual behaviour. Turns a
        // logcat dump from five separate booleans someone has to mentally
        // combine into one glance-able progression.
        val trackPhase = when {
            !coverageOk -> "APPROACHING"
            !zoomSettled -> "SETTLING"
            !focusLocked -> "FOCUSING"
            !sharpEnough -> "SHARPENING"
            readyStreak > 0 -> "HOLDING(${readyStreak}/${REQUIRED_READY_TICKS})"
            else -> "FRAMING"
        }
        if (now - lastTrackingLogAt >= TRACKING_LOG_INTERVAL_MS) {
            lastTrackingLogAt = now
            Log.d(TAG, "tickJewel phase=$trackPhase coverage=${result.coverage} colourOccupancy=$colourOccupancy mlOccupancy=$mlOccupancy zoom=$zoom coverageOk=$coverageOk bounds=${b?.let { "[${it.x0},${it.y0},${it.x1},${it.y1}] cx=${(it.x0+it.x1)/2f} cy=${(it.y0+it.y1)/2f}" } ?: "null"}")
        }

        // isCenteredNow() folded in here, not just checked once right before
        // firing -- confirmed live (2026-08-18): bounds cx can drift steadily
        // across several seconds with the gimbal completely idle (pair
        // detection flickering between "both studs"/"just one"), so a
        // single instant-of-capture check could catch it mid-drift,
        // transiting through the deadband rather than genuinely settled
        // there. Requiring REQUIRED_READY_TICKS consecutive centered ticks,
        // same as coverage/focus/sharpness already get, means a transient
        // pass-through no longer counts.
        // Same shape sanity check as waitForStableFrame's angle1/angle2 gate
        // (see CategoryOrientation.looksWrongShape's doc comment) -- MAIN
        // can hit the identical failure mode, a tracked box that's fully
        // inside frame and clears coverage/focus/sharp but is locked onto
        // the wrong sub-part of the piece.
        val wrongShapeRaw = CategoryOrientation.looksWrongShape(resolvedCategoryKey, result.bounds)
        val aiShapeOverrideActive = resolvedCategoryKey != null &&
            resolvedCategoryKey == aiShapeAdviceCategory && now < aiShapeOverrideUntil
        val wrongShape = wrongShapeRaw && !aiShapeOverrideActive
        if (!wrongShapeRaw) wrongShapeSince = 0L
        // Exempt once EV compensation has already hit its floor -- that
        // means applyAutoExposure() has corrected as much as this device
        // physically allows and the highlight is still clipping (a genuine
        // ambient-light problem, not something waiting-longer fixes).
        // Blocking forever on an uncorrectable glare would just stall the
        // item; every OTHER gate here already has the same fail-open
        // instinct once its own corrective mechanism is exhausted.
        val exposureExhausted = cameraExposureControlAvailable() &&
            autoExposureEv <= max(cameraExposureRangeEv().start, EXPOSURE_MIN_EV) + 0.05f
        if (coverageOk && !edgeClipped && !wrongShape && (!goldOverexposed || exposureExhausted) &&
            zoomSettled && focusLocked && sharpEnough && isCenteredNow()) {
            // Require this to hold for a few consecutive ticks, not just one
            // instant read -- a single tick can catch a momentarily-still
            // hand between small shakes, and the few hundred ms the shutter
            // then takes internally (CAPTURE_MODE_MAXIMIZE_QUALITY has real
            // pipeline latency) is enough time to drift back into blur
            // before the sensor actually exposes.
            readyStreak += 1
            if (readyStreak < REQUIRED_READY_TICKS) {
                setStatus("Holding steady…", ready = false)
                return
            }
            if (rsc2.isReady && attemptCenteringCorrection(result)) {
                readyStreak = 0
                return
            }
            readyStreak = 0
            centeringAttempts = 0
            if (!meetsHardCaptureRules()) {
                // Non-negotiable: centering conceded (deadband reached or
                // attempts exhausted) but the object still isn't ≥75% of
                // frame AND centered together -- don't capture. Next tick
                // re-enters this branch with a fresh centering budget.
                setStatus("Adjusting framing…", ready = false)
                return
            }
            setStatus("Ready. Capturing…", ready = true)
            captureJewel()
            return
        }
        // Decrement, don't hard-reset to 0 -- confirmed live (2026-08-18)
        // that coverage/bounds from the colour-only detector genuinely
        // flickers tick to tick even on a stationary, well-lit, in-focus
        // piece (af=LOCKED, sharp=100 the whole time, coverage bouncing a
        // few percent either side of the threshold). A hard reset meant
        // ANY single noisy tick among mostly-good ones wiped the whole
        // streak, so REQUIRED_READY_TICKS consecutive good ticks in a row
        // never accumulated -- "Holding steady…" forever with a genuinely
        // good shot sitting right there. Decrementing tolerates the odd
        // bad tick while still requiring sustained quality overall.
        readyStreak = (readyStreak - 1).coerceAtLeast(0)

        if (edgeClipped) {
            // NOT gated on coverageOk (2026-08-28 fix, live-confirmed on a
            // long mala/chain): the zoom-in climb below only stops once
            // AREA occupancy crosses CAPTURE_MIN_OCCUPANCY, with no
            // awareness of the box already touching an edge. A long thin
            // item's clipped area can still read well under that
            // threshold, so gating this on coverageOk let the climb keep
            // zooming PAST the point of clipping, chasing an area target
            // this item's own aspect ratio could never reach without
            // running off the top/bottom first. Checking edgeClipped here,
            // before the climb block below, stops the zoom-in the moment
            // clipping starts -- matching what StandDistanceGuide's "MOVE
            // STAND FARTHER" banner is already telling the operator,
            // instead of the climb fighting that guidance every tick.
            Log.i(TAG, "edgeClipped category=$resolvedCategoryKey coverageOk=$coverageOk zoom=$zoom bounds=$b")
            setStatus("Too close — zoom out or reposition", ready = false)
            return
        }

        if (coverageOk && wrongShape) {
            // Otherwise on track (coverage/focus climb wouldn't stall on
            // this) but the tracked box's own proportions don't match this
            // category -- give staff an explicit reason instead of a
            // silently-stuck "Framing…" they can't act on.
            b?.let { bounds ->
                val w = bounds.x1 - bounds.x0
                val h = bounds.y1 - bounds.y0
                val range = CategoryOrientation.GATE_WORTHY_ASPECT[resolvedCategoryKey]
                Log.i(
                    TAG,
                    "wrongShape category=$resolvedCategoryKey ratio=${if (h > 0f) w / h else -1f} " +
                        "w=$w h=$h expectedRange=$range"
                )
            }
            // Local-AI fallback (AiAdvisor.kt) -- only after this has
            // persisted a while, not on the first tick: a single noisy
            // aspect-ratio read isn't worth a round trip to the shared
            // local Ollama instance. One in-flight call at a time; a miss
            // or timeout just leaves the geometric gate as the final word,
            // since this is advisory only.
            if (wrongShapeSince == 0L) wrongShapeSince = now
            val categoryKey = resolvedCategoryKey
            if (now - wrongShapeSince >= WRONG_SHAPE_AI_FALLBACK_MS &&
                !aiShapeAdviceInFlight && categoryKey != null
            ) {
                val label = CaptureCompositionProfiles.forCategory(categoryKey)?.label ?: categoryKey
                val jpeg = sonyProduction.currentLiveViewJpeg()
                if (jpeg != null) {
                    aiShapeAdviceInFlight = true
                    wrongShapeSince = now + WRONG_SHAPE_AI_COOLDOWN_MS
                    lifecycleScope.launch {
                        val matches = try {
                            AiAdvisor.adviseShape(serverUrl(), label, jpeg)
                        } finally {
                            aiShapeAdviceInFlight = false
                        }
                        Log.i(TAG, "AiAdvisor shape category=$categoryKey matches=$matches")
                        if (matches == true && resolvedCategoryKey == categoryKey) {
                            aiShapeAdviceCategory = categoryKey
                            aiShapeOverrideUntil = System.currentTimeMillis() + AI_SHAPE_OVERRIDE_MS
                        }
                    }
                }
            }
            setStatus("Reposition — tracking looks off", ready = false)
            return
        }

        if (coverageOk && goldOverexposed && !exposureExhausted) {
            // applyAutoExposure() above is already stepping EV down --
            // this just holds the shutter until it's actually taken effect
            // instead of firing on a highlight it hasn't corrected yet.
            setStatus("Reducing glare…", ready = false)
            return
        }

        if (!coverageOk) {
            // Long items go straight to the zoom floor instead of ever
            // climbing in (2026-08-28): coverageOk already treats "at
            // floor" as satisfied for these categories, but a long item
            // that ARRIVES here still zoomed in from a previous item needs
            // to actively retreat, not fall into the normal climb-in logic
            // below (which would push zoom the wrong direction first).
            if (isLongItemCategory && !atZoomFloor) {
                if (now - lastZoomChangeAt < ZOOM_STEP_INTERVAL_MS) {
                    setStatus("Zooming out…", ready = false)
                    return
                }
                val next = (zoom / ZOOM_STEP_RATIO).coerceAtLeast(zoomRange.start)
                if (next < zoom - 0.01f) {
                    smoothZoomTo(next)
                    setStatus("Zooming out…", ready = false)
                    return
                }
            }
            // Too small to trust a focus verdict either way yet -- climb on
            // coverage alone, same reasoning as the web version's identical
            // branch (a crop this small would be judged on an upscaled,
            // artificially-softened analysis region). Deliberately does NOT
            // touch focus here at all -- that used to fire on every single
            // climb step (a new AF trigger roughly every tick, each one
            // interrupting whatever partial scan the last step started),
            // which is what "focus hunting too rapid" actually was. Focus
            // is only ever triggered once coverage is trustworthy AND the
            // zoom has been sitting still for ZOOM_SETTLE_MS, see below.
            if (now - lastZoomChangeAt < ZOOM_STEP_INTERVAL_MS) {
                setStatus("Zooming in…", ready = false)
                return
            }
            // Ported from the DINO/MIL branch's VisionServoController
            // (2026-08-18) -- see ZOOM_ALLOW_DEADBAND's doc comment. Holds
            // the zoom step (not the whole tick -- centering above already
            // ran concurrently this tick regardless) while the object is
            // still far off-center, so zoom can't race ahead of a slow
            // pan/tilt correction and clip the target at the frame edge.
            if (!isRoughlyCenteredForZoom()) {
                setStatus("Centering before zooming…", ready = false)
                return
            }
            // Must also respect maxUsableZoom -- a level a previous backoff
            // already proved unfocusable. Without this the climb ignored
            // that ceiling entirely and marched straight back up to the
            // exact same problem zoom every time, failed focus again,
            // backed off again, forever: the "zooms in, zooms back out,
            // keeps cycling" loop.
            val climbCeiling = effectiveZoomCeiling
            val next = (zoom * ZOOM_STEP_RATIO).coerceAtMost(climbCeiling)
            if (next > zoom + 0.01f) {
                smoothZoomTo(next)
                stepFocusAttempts = 0
                focusTriggeredThisLevel = false
                focusEvaluationNotBefore = 0L
                setStatus("Zooming in…", ready = false)
                return
            }
        }

        // Coverage is trustworthy now. Still give the lens/sensor a moment
        // to settle from the last zoom change before touching focus at all
        // -- triggering AF against a target that's still moving is judged
        // on a moving target and reads as more hunting.
        if (!zoomSettled) {
            setStatus("Zooming in…", ready = false)
            return
        }

        if (!focusTriggeredThisLevel) {
            // One decisive trigger per zoom level -- not re-fired every
            // tick while waiting for its result, that restart-storm was
            // the other half of the hunting complaint.
            val focusTarget = jewelleryFocusTarget(result)
            focusTriggeredThisLevel = triggerCameraAutoFocus(
                physicalSony = activeCameraSource == ProductionCameraSource.SONY,
                normalizedX = focusTarget?.x,
                normalizedY = focusTarget?.y
            )
            if (focusTriggeredThisLevel) {
                focusEvaluationNotBefore = now + FOCUS_EVALUATION_DELAY_MS
            }
            setStatus("Focusing…", ready = false)
            return
        }

        if (now < focusEvaluationNotBefore) {
            setStatus("Focusing…", ready = false)
            return
        }

        if (afState == null) {
            // Trigger already sent -- waiting for Camera2's own result,
            // not re-triggering.
            setStatus("Focusing…", ready = false)
            return
        }
        if (!focusLocked || !sharpEnough) {
            if (focusFailed || !sharpEnough) {
                // Never hammer AF repeatedly at an unfocusable magnification.
                // Step optically wider, settle, aim at the same real-gold
                // target and try once at the new level. maxUsableZoom makes
                // the failed level a hard ceiling so the climb cannot undo
                // the backoff and oscillate.
                if (backOffOneZoomForFocus()) {
                    return
                }
                focusTriggeredThisLevel = true
                setStatus("Still blurred at full wide — move the stand slightly back", ready = false)
                return
            }
            setStatus("Focusing…", ready = false)
            return
        }
    }

    /** ML Kit detected-object box (upright-normalized, same space the
     * on-screen overlay already trusts) that actually contains gold/warm
     * MaterialDetector points -- NOT just the largest box, and NEVER a
     * non-gold fallback. Every consumer of this function (arm gate,
     * zoom-climb occupancy, the occupancy hard capture gate, centering) is
     * gold-exclusive by construction: they all read this one function.
     *
     * Real bug found live (2026-08-18): with the original "just pick the
     * biggest box" heuristic, ML Kit's generic (colour-blind) object
     * detector reporting a large prop/display box as a detected object
     * always won over a small actual ring -- coverage stayed near zero,
     * centering never converged, capture never fired. Fixed to gold-
     * exclusive: this returns null, not a substitute object, whenever
     * there's no real gold evidence. Every caller already fails closed on
     * null -- that's exactly correct here: better to stall/re-search than
     * to center/zoom/capture against the wrong object. */
    private fun bestObjectBox(): RectF? = if (ML_KIT_OBJECT_DETECTION_ENABLED) bestGoldObjectBox() else null

    /** Same ML Kit box selection as bestObjectBox(), but returns null
     * (never a fallback) when no candidate box actually contains gold/warm
     * MaterialDetector points this tick. */
    private fun bestGoldObjectBox(): RectF? {
        val boxes = latestObjectBoxesUpright
        if (boxes.isEmpty()) return null
        // Gold-hue points ONLY, never silver/sparkle -- per the standing
        // "focus on gold only, always" rule. Silver's classifier is loose
        // enough to catch ordinary specular highlights (a glossy display
        // box's lit edge), which the raw "metal" point set doesn't
        // distinguish from real jewellery. Confirmed live (2026-08-18):
        // with literally no ornament in frame, points from the box's shiny
        // top edge still armed the tracker until this filter was added.
        val points = latestMaterial?.points?.filter { it.gold }
        if (points.isNullOrEmpty()) return null
        val rotation = lastMaterialRotationDegrees
        // Density (points / box area), NOT raw point count. A large object
        // (e.g. the display box) accumulates more stray metal-look points
        // than a small ring purely from having more surface area -- even a
        // handful of specular-highlight false positives on its glossy edges
        // can outscore a ring's real points on a raw-count basis. Confirmed
        // live (2026-08-18): the tracker locked onto the display box's
        // reflective edge instead of the (absent) ring, because the box had
        // more total warm/silver points than any small candidate box did.
        // Density fixes this: a small box that's mostly real metal wins
        // over a large box that's mostly not, regardless of point totals.
        //
        // Spatial continuity: once locked onto an object, only candidates
        // near its last-known position are eligible -- a real showroom has
        // OTHER real gold jewellery in it (display cases, other pieces),
        // and pure density can legitimately favor one of those over the
        // item actually in the capture box the instant the gimbal drifts
        // even slightly. Confirmed live (2026-08-18): centering kept
        // "succeeding" against whatever gold cluster scored highest each
        // tick, walked the gimbal off the ring in the capture box and onto
        // full display cases across the room. MAX_TARGET_JUMP is generous
        // (a third of the frame) so real tracking of an object moving/
        // zooming tick-to-tick is never blocked, but a jump across the
        // whole room is rejected -- return null (lost) so the caller's
        // existing lost-target recovery handles it, rather than silently
        // re-seeding onto something else.
        val anchor = lockedBoxCenter
        var bestBox: RectF? = null
        var bestDensity = 0f
        for (box in boxes) {
            val count = points.count { p ->
                val up = uprightPoint(p, rotation)
                box.contains(up[0], up[1])
            }
            if (count == 0) continue
            if (anchor != null) {
                val bcx = (box.left + box.right) / 2f
                val bcy = (box.top + box.bottom) / 2f
                val jump = kotlin.math.hypot((bcx - anchor.x).toDouble(), (bcy - anchor.y).toDouble()).toFloat()
                if (jump > MAX_TARGET_JUMP) continue
            }
            val rawArea = box.width() * box.height()
            val area = if (rawArea > 1e-4f) rawArea else 1e-4f
            val density = count / area
            if (density > bestDensity) {
                bestDensity = density
                bestBox = box
            }
        }
        if (bestBox != null) {
            val cx = (bestBox.left + bestBox.right) / 2f
            val cy = (bestBox.top + bestBox.bottom) / 2f
            lockedBoxCenter = android.graphics.PointF(cx, cy)
        }
        return bestBox
    }

    /** Continuously steers the AF/AE tracking region at wherever the
     * ornament currently is -- called every tick once armed, including
     * while the gimbal is mid-move, so continuous AF follows the object
     * through motion instead of losing it and having to re-search once
     * the gimbal stops. Prefers ML Kit's real box, falls back to
     * MaterialDetector's bounds, no-ops if neither has anything this tick
     * (nothing to steer toward). */
    private fun updateTrackingRegionFor(result: MaterialDetector.Result?) {
        val box = bestObjectBox()
        val cx: Float
        val cy: Float
        if (box != null) {
            cx = (box.left + box.right) / 2f
            cy = (box.top + box.bottom) / 2f
        } else {
            val bounds = result?.bounds ?: return
            cx = (bounds.x0 + bounds.x1) / 2f
            cy = (bounds.y0 + bounds.y1) / 2f
        }
        updateCameraTrackingRegion(cx, cy)
    }

    /** Automated exposure control (2026-08-18): steps exposure
     * compensation down when reflections are blowing out gold detail,
     * back up toward 0 when they aren't -- see the constants' doc
     * comment for the actual thresholds/reasoning. Reads
     * MaterialDetector.Result.highlightClipFraction (computed for free
     * during the existing gold-detection YUV sampling pass, no extra
     * image analysis added). Rate-limited via EXPOSURE_ADJUST_INTERVAL_MS
     * so it doesn't fight the camera's own AE convergence tick to tick.
     * No-ops entirely if the device didn't report a usable compensation
     * range (exposureControlAvailable() false) -- fails open rather than
     * guessing at unsupported values. */
    private fun applyAutoExposure(result: MaterialDetector.Result) {
        if (manualExposureOverride || !cameraExposureControlAvailable() ||
            !isTrustedMaterialTarget(result)
        ) {
            exposureClipStreak = 0
            exposureClearStreak = 0
            return
        }
        val now = System.currentTimeMillis()
        val adjustInterval = if (activeCameraSource == ProductionCameraSource.SONY) {
            SONY_EXPOSURE_ADJUST_INTERVAL_MS
        } else EXPOSURE_ADJUST_INTERVAL_MS
        if (now - lastExposureAdjustAt < adjustInterval) return
        lastExposureAdjustAt = now
        // Production's exact two-signal design (2026-08-18, restored
        // 2026-08-26): gold clipping AT ALL (>0f) means real design detail
        // (engraving/facets) is already lost there -- no percentage floor
        // makes sense for that judgment. sceneClipFraction (the whole
        // sampled region, not just gold) catches a washed-out BACKGROUND
        // even when the gold itself isn't clipping yet -- gold samples are
        // sparse per frame, so gold-only ever reacting is what silently
        // broke this (confirmed live both in 2026-08-18's original bug and
        // in this branch's regression of it).
        val goldOverexposed = result.highlightClipFraction > 0f
        val range = cameraExposureRangeEv()
        val floor = max(range.start, EXPOSURE_MIN_EV)
        val before = autoExposureEv
        val target = when {
            goldOverexposed || result.sceneClipFraction > HIGHLIGHT_CLIP_HIGH ->
                (before - EXPOSURE_STEP_EV).coerceAtLeast(floor)
            !goldOverexposed && result.sceneClipFraction < HIGHLIGHT_CLIP_LOW && before < 0f ->
                (before + EXPOSURE_STEP_EV).coerceAtMost(0f)
            else -> before
        }
        if (target != before) queueAutoExposure(target)
        Log.d(TAG, "applyAutoExposure goldClip=${result.highlightClipFraction} sceneClip=${result.sceneClipFraction} before=$before target=$target floor=$floor")
    }

    /** Latest-wins exposure queue. Do not update state until Sony ACKs. */
    private fun queueAutoExposure(targetEv: Float) {
        if (activeCameraSource != ProductionCameraSource.SONY) {
            autoExposureEv = targetEv
            setCameraExposureCompensationEv(targetEv)
            return
        }
        if (!exposureCommandInFlight && pendingAutoExposureEv == null && targetEv == autoExposureEv) {
            return
        }
        pendingAutoExposureEv = targetEv
        if (!exposureCommandInFlight) drainAutoExposureQueue()
    }

    private fun drainAutoExposureQueue() {
        val target = pendingAutoExposureEv ?: return
        pendingAutoExposureEv = null
        exposureCommandInFlight = true
        sonyProduction.setExposureCompensationEv(target) { ok ->
            if (ok) autoExposureEv = target
            exposureCommandInFlight = false
            if (!ok) Log.w(TAG, "Sony auto exposure command failed target=$target")
            if (pendingAutoExposureEv != null && pendingAutoExposureEv != autoExposureEv) {
                drainAutoExposureQueue()
            }
        }
    }

    /** The NON-NEGOTIABLE capture rules: the gimbal must not be mid-move
     * (tracking continues through motion, capture never does -- see
     * RSC2Controller.isMoving), the ornament must occupy at least
     * CAPTURE_MIN_OCCUPANCY of the full frame (checked via ML Kit's box
     * specifically -- see its doc comment), AND be centered within
     * CENTERING_DEADBAND on both axes ("centered from all 4 sides" is
     * exactly what a small centre-offset means for a bounding box: if the
     * box's center sits at true frame-center, its margins on all 4 edges
     * are equal by construction). No caller may bypass this for an
     * automatic capture -- only the manual-shutter override (an explicit
     * staff decision) skips it. Falls back to MaterialDetector's own
     * colour/contrast bounds (result.bounds) when ML Kit is disabled
     * (ML_KIT_OBJECT_DETECTION_ENABLED = false, 2026-08-18) or simply
     * hasn't found a box yet -- fails closed (returns false) only when
     * NEITHER source has anything, since occupancy can't be verified with
     * no box at all. */
    /** Smoothed centering test shared by meetsHardCaptureRules() and
     * tickJewel()'s readyStreak gate -- see centerEmaCx/Cy's doc comment
     * for why raw per-tick bounds can't be trusted alone. Confirmed live
     * (2026-08-18): even the EMA wasn't enough on its own -- bounds cx
     * drifted steadily across ~8 consecutive ticks (~1.2s) with the gimbal
     * completely idle and zoom pinned (the pair-detection flickering
     * between "both studs" and "just one" as one component's size dipped
     * below the pair-union threshold tick to tick), so a single
     * instant-of-capture centering check could still catch it mid-drift,
     * transiting through the deadband rather than actually settled there.
     * Folding this into readyStreak (same REQUIRED_READY_TICKS consecutive
     * ticks already required for coverage/focus/sharpness) means a capture
     * only fires once centering has genuinely HELD, not just touched,
     * the deadband. */
    /** Updates and returns the smoothed centre estimate from whatever raw
     * box is available this tick (mlBox, else result?.bounds, else
     * latestMaterial's). Returns null only when NEITHER source has
     * anything -- same "truly lost" bar as everywhere else in this file.
     * Single source of truth for centerEmaCx/Cy so every caller (the
     * capture gate AND the gimbal nudge logic) reacts to the same damped
     * signal. Confirmed live (2026-08-18): smoothing only the CAPTURE gate
     * wasn't enough -- attemptCenteringCorrection() was still reading raw,
     * unsmoothed bounds every tick, so a single noisy "just one stud
     * detected, not the pair" tick could still trigger a full, physically
     * large gimbal nudge (duration scales with the raw offset) chasing
     * that one bad reading. That's what "aggressively drifts in the last
     * few seconds" actually was: the gimbal being yanked back and forth by
     * detection noise, not just a reading that occasionally misjudged
     * "centered enough". Smoothing before the nudge decision as well means
     * a one-tick flicker only nudges the EMA a little, not the camera a lot. */
    private fun smoothedCenter(result: MaterialDetector.Result? = null): Pair<Float, Float>? {
        val mlBox = bestObjectBox()
        val cx: Float
        val cy: Float
        if (mlBox != null) {
            // latestObjectBoxesUpright is already upright (name says so,
            // and that's the whole reason uprightPoint() exists -- to bring
            // raw `points` into this SAME space for containment tests
            // elsewhere). No further correction needed here.
            cx = (mlBox.left + mlBox.right) / 2f
            cy = (mlBox.top + mlBox.bottom) / 2f
        } else {
            // REVERTED (2026-08-18): tried applying uprightPoint()'s
            // rotation correction here on the theory that result.bounds is
            // raw-sensor-frame while pan/tilt sign conventions assume
            // upright. Live test result: pan nudges made dx monotonically
            // WORSE every single time (0.06 -> 0.13 across 18 straight
            // nudges, never once correcting), then tilt did the same in the
            // other direction and drove the gimbal into its hard tilt
            // limit. That means either result.bounds is NOT actually raw
            // (something upstream already normalizes it -- the
            // updateTrackingRegion() doc comment claims bounds are already
            // upright, which may in fact be correct), or the empirically-
            // tuned pan/tilt sign conventions in attemptCenteringCorrection()
            // implicitly assume the OLD uncorrected axis and would need
            // their own resign, not just the input coordinates. Don't
            // reapply this without confirming lastMaterialRotationDegrees'
            // actual runtime value AND re-deriving the pan/tilt sign
            // convention from scratch against it -- guessing again risks
            // another hard-stop drive.
            val bounds = (result?.bounds ?: latestMaterial?.bounds) ?: return null
            cx = (bounds.x0 + bounds.x1) / 2f
            cy = (bounds.y0 + bounds.y1) / 2f
        }
        val EMA_ALPHA = 0.3f
        centerEmaCx = centerEmaCx?.let { it + (cx - it) * EMA_ALPHA } ?: cx
        centerEmaCy = centerEmaCy?.let { it + (cy - it) * EMA_ALPHA } ?: cy
        return centerEmaCx!! to centerEmaCy!!
    }

    private fun isCenteredNow(): Boolean {
        val (ecx, ecy) = smoothedCenter() ?: return false
        return abs(ecx - 0.5f) <= CENTERING_DEADBAND && abs(ecy - 0.5f) <= CENTERING_DEADBAND
    }

    /** Looser than isCenteredNow() -- see ZOOM_ALLOW_DEADBAND's doc comment.
     * Gates whether the zoom-climb may take its next step at all, not
     * capture readiness. Defaults to true (permissive) when there's no
     * position estimate at all, matching the zoom-climb's existing
     * behaviour of climbing on coverage alone before a box is trustworthy
     * -- this only needs to STOP the climb once a real, uncorrected offset
     * is known, not invent a reason to stall with nothing to go on. */
    private fun isRoughlyCenteredForZoom(): Boolean {
        val (ecx, ecy) = smoothedCenter() ?: return true
        return abs(ecx - 0.5f) <= ZOOM_ALLOW_DEADBAND && abs(ecy - 0.5f) <= ZOOM_ALLOW_DEADBAND
    }

    private fun meetsHardCaptureRules(): Boolean {
        if (rsc2.isReady && rsc2.isMoving) return false
        val mlBox = bestObjectBox()
        val occupancy: Float
        if (mlBox != null) {
            occupancy = mlBox.width() * mlBox.height()
        } else {
            val bounds = latestMaterial?.bounds ?: return false
            occupancy = bounds.area()
        }
        // Relax the occupancy floor once genuinely at the zoom ceiling --
        // matches the zoom-climb's OWN documented intent ("at the ceiling,
        // accept whatever coverage is on offer as the best framing
        // available... every capture still goes through the same
        // focusLocked + sharpEnough gate"), which this function was
        // silently NOT honoring: it had no ceiling escape of its own, so
        // coverageOk could read true via the ceiling while this still
        // failed on real occupancy, forever. Confirmed live (2026-08-18):
        // af=LOCKED, sharp=100, zoom pinned at maxUsableZoom=2.9 (a stale
        // per-item cap from an earlier failed-focus backoff), real
        // occupancy ~8-9% -- permanent "Adjusting framing" / "Holding
        // steady" cycle with a shot that was never going to get any
        // bigger at this position. Centering is NOT relaxed here --
        // only occupancy.
        val zoom = cameraZoomRatio()
        val zoomRange = cameraZoomRange()
        // Split what used to be one combined "atZoomCeiling" check
        // (2026-08-19, real production finding, tag GR22/127): a HARDWARE
        // ceiling (device physically cannot zoom further) is a genuine
        // "nothing more we can do" case, fine to accept as-is. But
        // maxUsableZoom is a SELF-IMPOSED backoff this app applies after
        // repeated focus failures at a given zoom level -- and on this
        // phone's macro-pinned physical sensor (~10cm minimum focus
        // distance), that almost always means the item was placed CLOSER
        // than the lens can focus at all, not that more zoom wasn't
        // available. Treating that the same as a hardware ceiling silently
        // accepted a tiny, design-detail-poor frame (confirmed live:
        // GR22/127 captured at ~7% occupancy this way) when the real fix
        // was simply "move the item back a little" -- fixable, not a
        // hardware limit.
        val atHardwareZoomCeiling = zoom >= min(zoomRange.endInclusive, MAX_LIVE_ZOOM_RATIO) - 0.02f
        val atUsableZoomCeiling = zoom >= maxUsableZoom - 0.02f
        if (occupancy < CAPTURE_MIN_OCCUPANCY) {
            if (atUsableZoomCeiling && !atHardwareZoomCeiling) {
                // Bounded grace window, not an outright block -- falls
                // back to the old accept-anyway behaviour after
                // MAX_USABLE_ZOOM_GRACE_MS so this can't regress into the
                // original 2026-08-18 infinite-stall bug this escape
                // hatch was built to fix. The window exists to give staff
                // a real chance to notice and reposition before a
                // marginal shot gets accepted.
                val now = System.currentTimeMillis()
                if (maxUsableZoomStuckSince == 0L) maxUsableZoomStuckSince = now
                if (now - maxUsableZoomStuckSince < MAX_USABLE_ZOOM_GRACE_MS) return false
            } else if (!atHardwareZoomCeiling) {
                return false
            }
        } else {
            maxUsableZoomStuckSince = 0L
        }
        return isCenteredNow()
    }

    /** Production arm check. MaterialDetector's [Result.material] is a
     * size/dominance threshold, not a presence signal: thin real jewellery
     * can have a stable gold-only [Result.bounds] and many gold samples while
     * its box area remains below that threshold. The Sony presence/AF path
     * already treats bounds as presence; keep the motion state machine in
     * agreement. Require several gold samples so one isolated warm pixel
     * cannot arm target-guided gimbal movement. Blind movement remains
     * independently hard-disabled by AUTONOMOUS_BLIND_HUNT_ENABLED. */
    private fun isTrustedMaterialTarget(material: MaterialDetector.Result): Boolean {
        val bounds = material.bounds ?: return false
        return bounds.area() >= MIN_TRUSTED_TARGET_AREA &&
            material.points.count { it.gold } >= MIN_TRUSTED_GOLD_POINTS
    }

    private fun detectedNow(): Boolean {
        val material = latestMaterial
        return (material != null && isTrustedMaterialTarget(material)) || bestObjectBox() != null
    }

    /** Active gimbal search for MAIN, used only once nothing has been
     * detected at all for HUNT_GRACE_MS -- rather than just waiting
     * indefinitely for the operator to reposition the item under a fixed
     * camera. Deterministic sweep order, exactly per spec:
     *   1. SCAN_DOWN -- tilt down from level, budget-limited (TILT_MS_LIMIT)
     *   2. RETURN_TILT -- back to level
     *   3. SCAN_LEFT -- pan left from center, budget-limited (HUNT_PAN_SWEEP_MAX_MS)
     *   4. RETURN_PAN -- back to center
     *   5. SCAN_RIGHT -- pan right from center, same budget
     *   6. GIVE_UP -- return home, let the operator reposition manually
     * Sequential single-axis steps only, same BLE-safety reasoning as
     * attemptCenteringCorrection() (each phase is broken into small steps,
     * not one giant burst, specifically so detection can be checked
     * between steps and the sweep stops "wherever, whenever" gold shows
     * up mid-motion). The instant detectedNow() fires, the sweep halts
     * immediately and hands off to tickJewel's normal armed path --
     * attemptCenteringCorrection's one-axis-at-a-time center/zoom/focus
     * loop -- from wherever the piece was found. */
    private fun huntStep() {
        if (huntBusy) return
        if (detectedNow()) {
            resetHuntState()
            return
        }
        huntBusy = true
        setStatus(huntStatusText(), ready = false)
        when (huntPhase) {
            HuntPhase.SCAN_DOWN -> {
                if (huntPhaseMsSpent >= TILT_MS_LIMIT) {
                    huntPhase = HuntPhase.RETURN_TILT
                    huntBusy = false
                    huntStep()
                    return
                }
                val step = min(HUNT_STEP_MS, (TILT_MS_LIMIT - huntPhaseMsSpent).toLong())
                centeringTiltMs -= step.toInt()
                huntPhaseMsSpent += step.toInt()
                val axis = DumlProtocol.AXIS_CENTER - HUNT_STEP_DEFLECTION
                rsc2.moveOut(axis1 = axis, durationMs = step) { huntBusy = false }
            }
            HuntPhase.RETURN_TILT -> {
                if (centeringTiltMs == 0) {
                    huntPhase = HuntPhase.SCAN_LEFT
                    huntPhaseMsSpent = 0
                    huntBusy = false
                    huntStep()
                    return
                }
                val undoTilt = if (centeringTiltMs > 0) DumlProtocol.AXIS_CENTER - CENTERING_DEFLECTION else DumlProtocol.AXIS_CENTER + CENTERING_DEFLECTION
                val durMs = abs(centeringTiltMs)
                centeringTiltMs = 0
                rsc2.moveOut(axis1 = undoTilt, durationMs = durMs.toLong()) {
                    huntBusy = false
                    huntStep()
                }
            }
            HuntPhase.SCAN_LEFT -> {
                if (huntPhaseMsSpent >= HUNT_PAN_SWEEP_MAX_MS) {
                    huntPhase = HuntPhase.RETURN_PAN
                    huntBusy = false
                    huntStep()
                    return
                }
                val step = min(HUNT_STEP_MS, (HUNT_PAN_SWEEP_MAX_MS - huntPhaseMsSpent).toLong())
                centeringPanMs -= step.toInt()
                huntPhaseMsSpent += step.toInt()
                val axis = DumlProtocol.AXIS_CENTER - HUNT_STEP_DEFLECTION
                rsc2.moveOut(axis3 = axis, durationMs = step) { huntBusy = false }
            }
            HuntPhase.RETURN_PAN -> {
                if (centeringPanMs == 0) {
                    huntPhase = HuntPhase.SCAN_RIGHT
                    huntPhaseMsSpent = 0
                    huntBusy = false
                    huntStep()
                    return
                }
                val undoPan = if (centeringPanMs > 0) DumlProtocol.AXIS_CENTER - CENTERING_DEFLECTION else DumlProtocol.AXIS_CENTER + CENTERING_DEFLECTION
                val durMs = abs(centeringPanMs)
                centeringPanMs = 0
                rsc2.moveOut(axis3 = undoPan, durationMs = durMs.toLong()) {
                    huntBusy = false
                    huntStep()
                }
            }
            HuntPhase.SCAN_RIGHT -> {
                if (huntPhaseMsSpent >= HUNT_PAN_SWEEP_MAX_MS) {
                    huntPhase = HuntPhase.GIVE_UP
                    huntBusy = false
                    huntStep()
                    return
                }
                val step = min(HUNT_STEP_MS, (HUNT_PAN_SWEEP_MAX_MS - huntPhaseMsSpent).toLong())
                centeringPanMs += step.toInt()
                huntPhaseMsSpent += step.toInt()
                val axis = DumlProtocol.AXIS_CENTER + HUNT_STEP_DEFLECTION
                rsc2.moveOut(axis3 = axis, durationMs = step) { huntBusy = false }
            }
            HuntPhase.GIVE_UP -> {
                huntBusy = false
                resetHuntState()
                huntCooldownUntil = System.currentTimeMillis() + HUNT_COOLDOWN_MS
                // Undoes whatever net pan/tilt the sweep left behind (should
                // already be ~0 after RETURN_TILT/RETURN_PAN, this is the
                // defensive belt-and-suspenders close-out) and returns home.
                undoCenteringThenAdvance {
                    setStatus("Not found — reposition the ornament", ready = false)
                }
            }
        }
    }

    private fun huntStatusText(): String = when (huntPhase) {
        HuntPhase.SCAN_DOWN -> "Searching below…"
        HuntPhase.RETURN_TILT -> "Returning to level…"
        HuntPhase.SCAN_LEFT -> "Searching left…"
        HuntPhase.RETURN_PAN -> "Returning to center…"
        HuntPhase.SCAN_RIGHT -> "Searching right…"
        HuntPhase.GIVE_UP -> "Returning home…"
    }

    private fun resetHuntState() {
        huntStartedAt = 0L
        huntPhase = HuntPhase.SCAN_DOWN
        huntPhaseMsSpent = 0
    }

    /** Nudge duration scaled to how far off-center the object is -- see
     * CENTERING_TICK_MS's doc comment for why a fixed duration was
     * measured too weak to close a large offset. Linear from
     * CENTERING_TICK_MS at magnitude=0 to CENTERING_TICK_MS_MAX at
     * magnitude=0.5 (half the frame, the worst realistic case), clamped
     * beyond that rather than extrapolating further. */
    private fun centeringDurationFor(magnitude: Float): Long {
        val t = (magnitude / 0.5f).coerceIn(0f, 1f)
        return (CENTERING_TICK_MS + t * (CENTERING_TICK_MS_MAX - CENTERING_TICK_MS)).toLong()
    }

    /**
     * Checks the detected ornament's position against true frame-center and,
     * if it's off by more than CENTERING_DEADBAND, issues ONE bounded
     * corrective nudge on tilt (axis1) and/or pan (axis3) and returns true
     * (caller should wait for the next tick rather than capture now). Once
     * within the deadband, or once CENTERING_MAX_ATTEMPTS is used up,
     * returns false so the caller proceeds to capture as-is -- this never
     * blocks a capture indefinitely on a correction that isn't converging.
     *
     * Prefers ML Kit's real detected-object box (bestObjectBox()) over
     * MaterialDetector's color/contrast bounds when available -- a genuine
     * object boundary rather than a gold-hue guess, and it works the same
     * for silver (MaterialDetector's colour heuristic is gold-biased and
     * gives silver pieces a weaker signal). Falls back to MaterialDetector's
     * bounds only on the rare frame where ML Kit hasn't found anything yet
     * (same fail-open pattern the dot-overlay filter above already uses).
     *
     * LIMITATION: these are velocity commands (see RSC2Controller), not
     * "move to this position" -- each nudge is a small fixed burst in a
     * direction, then re-measure. It is a real proportional-ish loop
     * (keeps nudging the same direction if still off after a nudge) but not
     * a precise servo; expect a few pixels of residual offset within the
     * deadband, not exact centering.
     */
    private fun attemptCenteringCorrection(
        result: MaterialDetector.Result,
        maxAttempts: Int = CENTERING_MAX_ATTEMPTS
    ): Boolean {
        if (centeringAttempts >= maxAttempts) return false
        // Confirmed live (2026-08-18): this had NO guard against issuing a
        // new nudge while the gimbal was still physically executing the
        // PREVIOUS one -- nudge durations run 300-500ms+, well past one
        // ~150-200ms tick, so the tick loop kept computing dx/dy from
        // mid-motion (sometimes motion-blurred) frames and firing another
        // command on top of one still in flight. rsc2.isMoving already
        // existed and was used to gate the final CAPTURE (meetsHardCapture-
        // Rules), just never here, where it actually matters most: this is
        // very likely the real cause of the oscillating, non-converging
        // corrections seen all session, independent of sign or duration
        // scaling -- confirmed correct via an isolated single-nudge BLE
        // test (axis3=1144 physically turned the gimbal right, which is
        // the correct direction to bring a right-of-center object toward
        // center). Returning false here (not incrementing any counters)
        // just means "wait, nothing to decide yet" -- the next tick tries
        // again once the gimbal reports settled.
        if (rsc2.isReady && rsc2.isMoving) return false
        if (System.currentTimeMillis() < centeringSettledUntil) return false

        // Safety check FIRST: if the last nudge this function issued was
        // followed by the ornament vanishing entirely (visible right
        // before that move, gone now), that move overshot it out of frame.
        // Undo just that one nudge and prefer the OTHER axis on the next
        // attempt, rather than continuing to push the axis that just lost
        // it. "What works" pattern per live testing: one axis at a time,
        // revert on loss, try the other axis next.
        if (lastCenterAxis != CenterAxis.NONE && bestObjectBox() == null &&
            !isTrustedMaterialTarget(result)
        ) {
            centeringAttempts += 1
            val axis = lastCenterAxis
            val sign = lastCenterSign
            val durMs = lastCenterDurationMs
            Log.i(TAG, "centering nudge lost the ornament -- reverting axis=$axis sign=$sign durMs=$durMs")
            centerAvoidAxis = axis
            lastCenterAxis = CenterAxis.NONE
            setStatus("Centering ornament…", ready = false)
            centeringSettledUntil = System.currentTimeMillis() + durMs + 400L
            if (axis == CenterAxis.PAN) {
                centeringPanMs -= sign * durMs
                val undoPan = if (sign > 0) DumlProtocol.AXIS_CENTER - CENTERING_DEFLECTION else DumlProtocol.AXIS_CENTER + CENTERING_DEFLECTION
                rsc2.moveOut(axis3 = undoPan, durationMs = durMs.toLong()) {}
            } else {
                centeringTiltMs -= sign * durMs
                val undoTilt = if (sign > 0) DumlProtocol.AXIS_CENTER - CENTERING_DEFLECTION else DumlProtocol.AXIS_CENTER + CENTERING_DEFLECTION
                rsc2.moveOut(axis1 = undoTilt, durationMs = durMs.toLong()) {}
            }
            return true
        }

        // Smoothed, not raw -- see smoothedCenter()'s doc comment. A nudge's
        // physical duration scales with abs(dx)/abs(dy), so feeding it a raw
        // single-tick reading let one noisy "detected only one stud, not
        // the pair" frame trigger a real, large gimbal move chasing it.
        val (cx, cy) = smoothedCenter(result) ?: return false
        val dx = cx - 0.5f
        val dy = cy - 0.5f
        val needsPan = abs(dx) > CENTERING_DEADBAND
        val needsTilt = abs(dy) > CENTERING_DEADBAND
        if (!needsPan && !needsTilt) { lastCenterAxis = CenterAxis.NONE; return false }

        // ONE axis per nudge, never both at once -- a combined tilt+pan
        // command triggered an immediate BLE disconnect in live testing
        // (the first time this app ever sent both axes deflected
        // simultaneously); every single-axis command all session was
        // reliable. Corrects whichever axis is off by more, UNLESS that
        // axis just reverted for overshooting (centerAvoidAxis) -- then the
        // other axis gets one turn first, if it also needs correcting.
        val avoid = centerAvoidAxis
        centerAvoidAxis = CenterAxis.NONE
        var choosePan = when {
            needsPan && avoid == CenterAxis.PAN && needsTilt -> false
            needsTilt && avoid == CenterAxis.TILT && needsPan -> true
            needsPan && (!needsTilt || abs(dx) >= abs(dy)) -> true
            else -> false
        }
        // Tilt is the one axis with a real mechanical hard-stop (see
        // TILT_MS_LIMIT). If tilt was chosen but its budget is exhausted,
        // fall back to pan when pan also needs correcting; otherwise this
        // attempt has nothing safe left to do.
        val tiltDurMs = centeringDurationFor(abs(dy))
        if (!choosePan) {
            val tiltSign = if (dy > 0) -1 else 1
            if (abs(centeringTiltMs + tiltSign * tiltDurMs) > TILT_MS_LIMIT) {
                if (needsPan) {
                    choosePan = true
                } else {
                    val now = System.currentTimeMillis()
                    if (now - lastCenterLimitLogAt >= TRACKING_LOG_INTERVAL_MS) {
                        lastCenterLimitLogAt = now
                        Log.w(TAG, "centering: tilt budget exhausted (ms=$centeringTiltMs) and pan not needed")
                    }
                    lastCenterAxis = CenterAxis.NONE
                    return false
                }
            }
        }
        // Pan had no equivalent budget cap at all until now. Same pattern
        // as tilt: exhausted budget falls back to the other axis if it
        // still needs correcting, else gives up this round rather than
        // pushing further. See PAN_MS_LIMIT's doc comment.
        if (choosePan) {
            val panDurMs = centeringDurationFor(abs(dx))
            val panSign = if (dx > 0) 1 else -1
            if (abs(centeringPanMs + panSign * panDurMs) > PAN_MS_LIMIT) {
                if (needsTilt) {
                    choosePan = false
                } else {
                    val now = System.currentTimeMillis()
                    if (now - lastCenterLimitLogAt >= TRACKING_LOG_INTERVAL_MS) {
                        lastCenterLimitLogAt = now
                        Log.w(TAG, "centering: pan budget exhausted (ms=$centeringPanMs) and tilt not needed")
                    }
                    lastCenterAxis = CenterAxis.NONE
                    return false
                }
            }
        }
        // Divergence circuit-breaker -- see the field doc comment. Checked
        // against whichever axis is about to be nudged; DIVERGE_LIMIT
        // consecutive same-axis nudges that don't measurably shrink the
        // error (a small tolerance, not a strict decrease, so genuine
        // slow-but-real convergence isn't mistaken for divergence) stops
        // that axis for the rest of this item rather than continuing to
        // push it further wrong.
        val axisAboutToNudge = if (choosePan) CenterAxis.PAN else CenterAxis.TILT
        val errorMagnitude = if (choosePan) abs(dx) else abs(dy)
        if (lastNudgeAxis == axisAboutToNudge) {
            val prior = lastNudgeErrorMagnitude
            if (prior != null && errorMagnitude >= prior - 0.005f) {
                centerDivergeStreak += 1
            } else {
                centerDivergeStreak = 0
            }
        } else {
            centerDivergeStreak = 0
        }
        val DIVERGE_LIMIT = 3
        if (centerDivergeStreak >= DIVERGE_LIMIT) {
            Log.w(TAG, "centering: $axisAboutToNudge not converging after $DIVERGE_LIMIT nudges (error stuck/growing at $errorMagnitude) -- giving up on this axis for this item")
            lastCenterAxis = CenterAxis.NONE
            lastNudgeAxis = CenterAxis.NONE
            lastNudgeErrorMagnitude = null
            centerDivergeStreak = 0
            return false
        }
        lastNudgeAxis = axisAboutToNudge
        lastNudgeErrorMagnitude = errorMagnitude

        centeringAttempts += 1
        setStatus("Centering ornament…", ready = false)
        if (choosePan) {
            // REVERTED (2026-08-18): flipping this made it categorically
            // worse -- dx got pinned at ~0.30 (object stuck near the frame
            // edge) and pan's budget blew straight through its cap
            // (centeringPanMs hit -10101 against a +-9000 limit) trying to
            // correct in the new direction. Back to the original sign.
            // Neither sign has actually been confirmed live yet -- the
            // "stuck/growing dx" the divergence breaker keeps catching is
            // real, but which direction is actually correct needs a
            // controlled single-nudge test (fire exactly one known-duration
            // pan command, screenshot before/after, confirm which way the
            // frame shifts) rather than inferring it from noisy multi-nudge
            // centering data, which is what led to the wrong call above.
            // Object right-of-center (dx>0) -> pan camera right to bring it
            // in. axis3 ABOVE center = the "right" direction.
            val sign = if (dx > 0) 1 else -1
            val durMs = centeringDurationFor(abs(dx))
            // Hard clamp regardless of the pre-check above -- confirmed live
            // (2026-08-18) centeringPanMs reached -10101 against a +-9000
            // limit by some path this session hasn't fully traced yet; this
            // guarantees it can never happen again even if that path
            // recurs, rather than relying solely on the pre-increment check.
            centeringPanMs = (centeringPanMs + sign * durMs.toInt()).coerceIn(-PAN_MS_LIMIT, PAN_MS_LIMIT)
            lastCenterAxis = CenterAxis.PAN
            lastCenterSign = sign
            lastCenterDurationMs = durMs.toInt()
            val panAxis = DumlProtocol.AXIS_CENTER + sign * CENTERING_DEFLECTION
            Log.i(TAG, "centering nudge #$centeringAttempts (pan) dx=$dx dy=$dy pan=$panAxis durMs=$durMs")
            // +400 matches moveOut()'s default settleMs -- see
            // centeringSettledUntil's doc comment.
            centeringSettledUntil = System.currentTimeMillis() + durMs + 400L
            rsc2.moveOut(axis3 = panAxis, durationMs = durMs) {}
        } else {
            // Object low-in-frame (dy>0, y grows downward) -> tilt camera
            // down. axis1 ABOVE center = look up (confirmed live).
            val sign = if (dy > 0) -1 else 1
            // Same defensive clamp as pan, see its comment above.
            centeringTiltMs = (centeringTiltMs + sign * tiltDurMs.toInt()).coerceIn(-TILT_MS_LIMIT, TILT_MS_LIMIT)
            lastCenterAxis = CenterAxis.TILT
            lastCenterSign = sign
            lastCenterDurationMs = tiltDurMs.toInt()
            val tiltAxis = DumlProtocol.AXIS_CENTER + sign * CENTERING_DEFLECTION
            Log.i(TAG, "centering nudge #$centeringAttempts (tilt) dx=$dx dy=$dy tilt=$tiltAxis durMs=$tiltDurMs")
            centeringSettledUntil = System.currentTimeMillis() + tiltDurMs + 400L
            rsc2.moveOut(axis1 = tiltAxis, durationMs = tiltDurMs) {}
        }
        return true
    }

    /** Undoes every nudge attemptCenteringCorrection() applied -- pan then
     * tilt, sequential single-axis moves, never combined (see above) --
     * before handing off to the TAG phase. Without this each item would
     * start further off-center than the last. */
    private fun undoCenteringThenAdvance(onDone: () -> Unit) {
        undoCenteringPan { undoCenteringTilt { onDone() } }
    }

    private fun undoCenteringPan(onDone: () -> Unit) {
        if (centeringPanMs == 0) { onDone(); return }
        val undoPan = if (centeringPanMs > 0) DumlProtocol.AXIS_CENTER - CENTERING_DEFLECTION else DumlProtocol.AXIS_CENTER + CENTERING_DEFLECTION
        val durMs = abs(centeringPanMs)
        Log.i(TAG, "undoing centering pan: ms=$centeringPanMs")
        rsc2.moveOut(axis3 = undoPan, durationMs = durMs.toLong()) {
            centeringPanMs = 0
            onDone()
        }
    }

    private fun undoCenteringTilt(onDone: () -> Unit) {
        if (centeringTiltMs == 0) { onDone(); return }
        val undoTilt = if (centeringTiltMs > 0) DumlProtocol.AXIS_CENTER - CENTERING_DEFLECTION else DumlProtocol.AXIS_CENTER + CENTERING_DEFLECTION
        val durMs = abs(centeringTiltMs)
        Log.i(TAG, "undoing centering tilt: ms=$centeringTiltMs")
        rsc2.moveOut(axis1 = undoTilt, durationMs = durMs.toLong()) {
            centeringTiltMs = 0
            onDone()
        }
    }

    private fun min(a: Float, b: Float) = if (a < b) a else b

    /** Converts a MaterialDetector.Point (normalized, raw sensor-space, same
     * as BoundsOverlayView receives) into the UPRIGHT/rotation-applied
     * normalized space ML Kit's bounding boxes are already in -- same
     * per-point transform BoundsOverlayView.update() uses for display, just
     * without the FILL_CENTER view-mapping step since this is purely for a
     * containment test, not drawing. */
    private fun uprightPoint(p: MaterialDetector.Point, rotationDegrees: Int): FloatArray = when (rotationDegrees) {
        90 -> floatArrayOf(1f - p.y, p.x)
        180 -> floatArrayOf(1f - p.x, 1f - p.y)
        270 -> floatArrayOf(p.y, 1f - p.x)
        else -> floatArrayOf(p.x, p.y)
    }

    /**
     * Ramps zoom from the current ratio to [target] over [durationMs] in
     * small sub-steps instead of one instant jump -- setZoomRatio() itself
     * doesn't animate, so every previous zoom change looked like a jerk
     * cut rather than a continuous glide. tickJewel skips entirely while
     * this is running (isZooming) and only starts settling once the ramp
     * actually finishes at [target], so ZOOM_SETTLE_MS always measures
     * quiet time from when the lens truly stopped moving.
     */
    private fun smoothZoomTo(target: Float, durationMs: Long = 260L, onDone: (() -> Unit)? = null) {
        val start = cameraZoomRatio()
        if (activeCameraSource == ProductionCameraSource.SONY) {
            // Sony PZ is velocity-driven. Completion comes from the actual
            // ZoomOperation response, never an optimistic timer/target.
            isZooming = true
            setCameraZoomRatio(target) { ok ->
                handler.postDelayed({
                    isZooming = false
                    lastZoomChangeAt = System.currentTimeMillis()
                    if (!ok) {
                        Log.w(TAG, "Sony physical zoom did not move start=$start target=$target")
                    }
                    onDone?.invoke()
                }, 180L)
            }
            return
        }
        val steps = 10
        val stepDelay = durationMs / steps
        isZooming = true
        var i = 0
        val ramp = object : Runnable {
            override fun run() {
                i += 1
                val t = i.toFloat() / steps
                // Ease-out: fast at first, settling gently into the target
                // rather than a linear ramp that feels mechanical.
                val eased = 1f - (1f - t) * (1f - t)
                setCameraZoomRatio(start + (target - start) * eased)
                if (i >= steps) {
                    isZooming = false
                    lastZoomChangeAt = System.currentTimeMillis()
                    onDone?.invoke()
                } else {
                    handler.postDelayed(this, stepDelay)
                }
            }
        }
        handler.postDelayed(ramp, stepDelay)
    }

    // ---------------------------------------------------------------- Capture + upload

    /** Opt-in only: defaults to false, so behavior is completely unchanged
     * unless explicitly enabled via BleDiagnosticsActivity's debug toggle
     * (never exposed on the live capture screen -- this is a testing path
     * while NothingCameraBridge is being validated against real capture
     * volume, not a default-flow replacement). */
    private fun useNothingCameraForCapture(): Boolean =
        getSharedPreferences("capturecam_debug", MODE_PRIVATE).getBoolean("use_nothing_camera", false)

    private fun captureJewel() {
        val captureFn: ((ByteArray?) -> Unit) -> Unit = if (useNothingCameraForCapture()) {
            { cb -> NothingCameraBridge.captureViaNothingCamera(this, cb) }
        } else {
            { cb -> captureFullRes(onResult = cb) }
        }
        captureFn jewelCapture@{ bytes ->
            if (bytes == null) {
                setStatus("Capture failed — retrying", ready = false)
                return@jewelCapture
            }
            // Logged for calibration only -- NOT used as a pass/fail gate.
            // The first attempt at a real threshold (300) was a guess from
            // extrapolating the low-res live scale, and it was wrong by two
            // orders of magnitude: real captures land at 0.6-15 raw, so
            // literally every photo failed regardless of actual sharpness
            // (this is what "even sharp images tagged as soft" was). Rather
            // than guess a second number blind, this gate is off until it
            // can be calibrated against labeled sharp-vs-blurred examples.
            // Real focus verification still comes from Camera2's actual
            // CONTROL_AF_STATE + the steady-hold debounce in tickJewel,
            // which ARE trustworthy.
            jewelCaptureRetries = 0
            jewelJpeg = bytes
            // Calibration only. Never hold the UI or captured-image choice
            // behind a full 26MP bitmap decode; the original JPEG bytes stay
            // untouched for saving/uploading.
            lifecycleScope.launch(Dispatchers.Default) {
                val opts = BitmapFactory.Options().apply { inSampleSize = 4 }
                val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts)
                val raw = bmp?.let { SharpnessAnalyzer.scoreBitmapRaw(it) }
                Log.i(TAG, "jewel capture sampled sharpness raw=$raw size=${bmp?.width}x${bmp?.height} liveSharp=$latestSharpness")
                bmp?.recycle()
            }
            showCapturePreview(
                bytes,
                onProceed = { onMainCaptureAccepted() },
                onComplete = { completeAfterMainCapture() },
                onRetake = { retakeJewel() },
                onCancel = { cancelItem() },
                requireManualConfirm = true
            )
        }
    }

    /**
     * MAIN shot accepted. If the RSC 2 is connected, continues into the
     * ANGLE_1/ANGLE_2 sequence before moving to the TAG phase; otherwise
     * falls straight through to the existing single-image TAG phase
     * unchanged -- the gimbal is additive, never required.
     *
     * ANGLE_1/ANGLE_2 are staff-driven, not a scripted gimbal sweep: the
     * operator physically rotates the ornament to show a side profile
     * (a real rotation of the piece, which panning a camera around a
     * stationary object can't replicate) and taps READY when it's
     * positioned. Only then does the gimbal act, and only to fine RE-CENTER
     * on wherever the piece ended up (see centerThenCapture), not to sweep
     * to a preset pose.
     */
    private fun onMainCaptureAccepted() {
        Log.i(TAG, "onMainCaptureAccepted: rsc2.isReady=${rsc2.isReady}")
        // rsc2.isReady is a live BLE-state check (commandCharacteristic !=
        // null && gatt != null), not debounced -- a momentary BLE blip
        // exactly at this instant used to permanently fall back to a
        // single-photo item with zero warning to staff. Confirmed live
        // (2026-08-19, tag WT22/6): item saved with just MAIN, no angle1/
        // angle2, no visible sign anything was different, discovered only
        // because staff noticed the app moved to the next item faster than
        // usual. Give the connection a short grace window to recover before
        // treating it as truly gone.
        waitForGimbalReady { ready ->
            if (!ready) {
                logCaptureEvent("gimbal_not_ready_single_photo_fallback")
                Toast.makeText(
                    this, "Gimbal not connected — saved MAIN photo only for this item",
                    Toast.LENGTH_LONG
                ).show()
                inAngleSequence = false
                uploadCapturedSet()
                return@waitForGimbalReady
            }
            onMainCaptureAcceptedWithGimbal()
        }
    }

    /** MAIN is sufficient for items without a multi-angle requirement. Keep
     * the same lossless single-image upload path; only restore any accumulated
     * gimbal correction before completing the item. */
    private fun completeAfterMainCapture() {
        Log.i(TAG, "completeAfterMainCapture: operator selected single-angle item")
        inAngleSequence = false
        setStatus("Completing item…", ready = false)
        undoCenteringThenAdvance { uploadCapturedSet() }
    }

    private fun waitForGimbalReady(attemptsLeft: Int = GIMBAL_READY_GRACE_ATTEMPTS, onResult: (Boolean) -> Unit) {
        if (rsc2.isReady) {
            onResult(true)
            return
        }
        if (attemptsLeft <= 0) {
            onResult(false)
            return
        }
        handler.postDelayed({ waitForGimbalReady(attemptsLeft - 1, onResult) }, GIMBAL_READY_GRACE_INTERVAL_MS)
    }

    private fun onMainCaptureAcceptedWithGimbal() {
        inAngleSequence = true
        promptForSideProfile("Turn the ornament to show a SIDE profile, then tap READY") {
            centerThenCapture { captureAngle1() }
        }
    }

    /** Gate before MAIN's auto-detect/hunt loop is allowed to run at all --
     * called right after tag capture, before resetForNewItem(Phase.JEWEL)
     * even flips the phase. Same READY-button pattern as
     * promptForSideProfile(), for the same reason: placing the item takes
     * real time, and the old behaviour (arm the JEWEL tick loop the
     * instant the tag was confirmed) let the hunt sweep start searching
     * for nothing before staff had physically placed anything. */
    private fun promptToPlaceMainItem() {
        jewelReadyPending = true
        setStatus("Place the ornament under the camera, then tap READY", ready = false)
        showReadyButton {
            jewelReadyPending = false
            setStatus("Center the ornament, front side up…", ready = false)
        }
    }

    /** Shows the instruction + big READY button and waits for the staff tap
     * before calling [onReady] -- no auto-timeout fire here, unlike the old
     * pan-sweep gate. The staff decides when the piece is actually
     * positioned; nothing should capture before that. */
    private fun promptForSideProfile(instruction: String, onReady: () -> Unit) {
        angleCaptureRetryCount = 0
        angleStableRefocusAttempts = 0
        setStatus(instruction, ready = false)
        showReadyButton {
            centeringAttempts = 0
            angleZoomRounds = 0
            angleFocusTriggered = false
            resetSonyAutomaticAfBudget()
            // Re-arms continuous AF as the baseline for this side's
            // tracking -- the MAIN capture's final triggerAutoFocus() lock
            // (or this same side's own, on a retake) does not resume
            // continuous scanning by itself.
            startCameraContinuousTracking()
            setStatus("Centering the ornament…", ready = false)
            onReady()
        }
    }

    private fun showReadyButton(onReady: () -> Unit) {
        pendingReadyAction = onReady
        binding.manualShutterButton.visibility = View.GONE
        binding.readyButton.visibility = View.VISIBLE
    }

    private fun hideReadyButton() {
        pendingReadyAction = null
        binding.readyButton.visibility = View.GONE
        binding.manualShutterButton.visibility = View.VISIBLE
    }

    /** Runs attemptCenteringCorrection() in a loop (single-axis nudge,
     * re-measure, repeat -- same fragile-BLE-safe primitive MAIN uses, see
     * its doc comment) until the ornament is within the centering deadband
     * or ANGLE_CENTERING_MAX_ATTEMPTS is exhausted, then re-triggers
     * autofocus and waits for a genuinely sharp, focus-locked frame
     * (waitForStableFrame) before calling [onCentered]. Staff-placed poses
     * can start much further off-center than MAIN's fine correction ever
     * has to travel, hence the larger attempt budget passed here. */
    private fun centerThenCapture(onCentered: () -> Unit) {
        // Zoom +/- is the explicit manual-mode switch. Angle capture used to
        // ignore it and keep issuing RemoteTouchOperation in the background,
        // so the lens visibly hunted even while the UI said "auto standing
        // by". Stand down completely; MANUAL CAPTURE routes to the active
        // side below.
        if (manualModeActive) {
            setStatus("Manual mode — tap MANUAL CAPTURE when sharp", ready = true)
            return
        }
        val result = latestMaterial
        // Continuous tracking follows the object through every nudge this
        // loop issues, including while the gimbal is physically still
        // moving from the last one -- meetsHardCaptureRules() (via
        // rsc2.isMoving) is what actually blocks capture during motion,
        // not this call; this just keeps AF/AE aimed at the right place
        // the whole time so there's nothing to re-acquire once it stops.
        updateTrackingRegionFor(result)
        if (result != null && isTrustedMaterialTarget(result) &&
            attemptCenteringCorrection(result, ANGLE_CENTERING_MAX_ATTEMPTS)) {
            angleFocusTriggered = false
            handler.postDelayed({ centerThenCapture(onCentered) }, CENTERING_TICK_MS + 200L)
            return
        }
        // Centering settled (or gave up) -- now chase the other
        // non-negotiable rule, occupancy. Bounded manual zoom-in step (see
        // ANGLE_ZOOM_MAX_ROUNDS); re-centers after each step since zooming
        // shifts framing, hence looping back through centerThenCapture
        // rather than just re-checking here.
        val occupancy = bestObjectBox()?.let { it.width() * it.height() }
        if ((occupancy == null || occupancy < CAPTURE_MIN_OCCUPANCY) && angleZoomRounds < ANGLE_ZOOM_MAX_ROUNDS) {
            val zoom = cameraZoomRatio()
            val zoomRange = cameraZoomRange()
            val next = (zoom * ZOOM_STEP_RATIO).coerceAtMost(
                min(min(zoomRange.endInclusive, MAX_LIVE_ZOOM_RATIO), maxUsableZoom)
            )
            if (next > zoom + 0.01f) {
                angleZoomRounds += 1
                angleFocusTriggered = false
                setStatus("Zooming in…", ready = false)
                smoothZoomTo(next) {
                    handler.postDelayed({ centerThenCapture(onCentered) }, ZOOM_SETTLE_MS)
                }
                return
            }
        }
        if (!angleFocusTriggered) {
            val focusTarget = jewelleryFocusTarget(latestMaterial)
            angleFocusTriggered = triggerCameraAutoFocus(
                physicalSony = activeCameraSource == ProductionCameraSource.SONY,
                normalizedX = focusTarget?.x,
                normalizedY = focusTarget?.y
            )
        }
        waitForStableFrame("Focusing…") {
            if (!meetsHardCaptureRules()) {
                // Non-negotiable: still not ≥75% of frame AND centered
                // together. Keep re-checking (centering budget refills
                // each call) rather than capturing out of compliance.
                setStatus("Adjusting framing…", ready = false)
                handler.postDelayed({ centerThenCapture(onCentered) }, 500L)
                return@waitForStableFrame
            }
            onCentered()
        }
    }

    /** Gate for angle1/angle2 shots -- mirrors tickJewel()'s MAIN-capture
     * gate (presence + focus-lock + sharpness, held for several consecutive
     * ticks) rather than just checking the ornament is somewhere in frame.
     * Still fails open at ANGLE_STABLE_TIMEOUT_MS so a stubborn low-texture
     * surface or a piece staff can't get sharp can't stall the item
     * forever -- it just captures the best frame on offer at that point. */
    private fun waitForStableFrame(instruction: String, onDetected: () -> Unit) {
        setStatus(instruction, ready = false)
        angleStableStreak = 0
        val deadline = System.currentTimeMillis() + ANGLE_STABLE_TIMEOUT_MS
        val check = object : Runnable {
            override fun run() {
                val result = latestMaterial
                // result?.material was the STRICTER threshold flag, same
                // class of bug already found and fixed in tickJewel() this
                // session: it can flicker false tick-to-tick on a
                // genuinely-present, well-detected piece (confirmed live
                // 2026-08-18 on a heavily faceted/engraved ring -- gold
                // dots clearly rendering on it, coverage genuinely low
                // enough that goldDominant/the coverage-ratio thresholds
                // never cleared, so `material` stayed false every single
                // tick and this loop never once saw "present", cycling
                // Focusing.../Adjusting framing... forever). Match
                // tickJewel()'s own "truly lost" bar instead: any position
                // estimate at all, not the stricter material flag.
                val present = bestObjectBox() != null || result?.bounds != null
                val focusLocked = isCameraFocusLocked(cameraAfState())
                val sharpEnough = latestSharpness >= SHARPNESS_THRESHOLD
                // Bracelet/bangle-shaped items can present as a bright band
                // the tracker locks onto and zooms into without ever
                // checking whether the band's own box has spilled off the
                // visible frame -- confirmed live 2026-08-19: coverage,
                // goldClip and sceneClip all read fine while the tracked
                // box ran edge-to-edge left-right at 3.4x zoom. Reject that
                // as "not really present" so READY never lights on a
                // clipped shot; the deadline below still fails open rather
                // than stalling forever on a piece too large for any zoom
                // level to fully frame.
                val edgeClipped = MaterialDetector.touchesFrameEdge(result?.bounds)
                // Catches the OTHER half of the 2026-08-19 bracelet bug:
                // even when the tracked box is fully inside the frame, it
                // can still be locked onto the wrong sub-part of the piece
                // (a thin highlight band instead of the whole bracelet).
                // touchesFrameEdge alone wouldn't catch that if the bad
                // box happened not to reach an edge.
                val wrongShape = CategoryOrientation.looksWrongShape(resolvedCategoryKey, result?.bounds)
                val now = System.currentTimeMillis()
                if (present && !edgeClipped && !wrongShape && focusLocked && sharpEnough) {
                    angleStableStreak += 1
                    if (angleStableStreak >= ANGLE_STABLE_TICKS) {
                        setStatus("Holding steady…", ready = true)
                        onDetected()
                        return
                    }
                } else {
                    angleStableStreak = 0
                }
                if ((edgeClipped || wrongShape) && now < deadline) {
                    if (wrongShape) result?.bounds?.let { bounds ->
                        val w = bounds.x1 - bounds.x0
                        val h = bounds.y1 - bounds.y0
                        val range = CategoryOrientation.GATE_WORTHY_ASPECT[resolvedCategoryKey]
                        Log.i(
                            TAG,
                            "wrongShape(angle) category=$resolvedCategoryKey ratio=${if (h > 0f) w / h else -1f} " +
                                "w=$w h=$h expectedRange=$range"
                        )
                    }
                    setStatus(
                        if (edgeClipped) "Too close — zoom out or reposition" else "Reposition — not fully in view",
                        ready = false
                    )
                    handler.postDelayed(this, 150L)
                    return
                }
                if (now >= deadline) {
                    angleStableRefocusAttempts += 1
                    Log.w(
                        TAG,
                        "waitForStableFrame timeout attempt=$angleStableRefocusAttempts " +
                            "present=$present edgeClipped=$edgeClipped focusLocked=$focusLocked " +
                            "sharp=$latestSharpness"
                    )
                    if (present && !edgeClipped && !wrongShape &&
                        backOffOneZoomForFocus {
                            angleFocusTriggered = false
                            handler.postDelayed(
                                { centerThenCapture(onDetected) },
                                ZOOM_SETTLE_MS
                            )
                        }
                    ) {
                        angleFocusTriggered = false
                    } else {
                        setStatus("Still blurred at full wide — adjust stand, then tap READY", ready = false)
                        showReadyButton {
                            angleStableRefocusAttempts = 0
                            angleFocusTriggered = false
                            centerThenCapture(onDetected)
                        }
                    }
                    return
                }
                handler.postDelayed(this, 150L)
            }
        }
        handler.post(check)
    }

    /** Cheap "did the item actually get moved between shots" check --
     * downsamples both JPEGs to a small grayscale grid and compares mean
     * absolute pixel difference. This is NOT a vision model or a precise
     * pose comparison; it exists to catch the specific operator mistake
     * this was built for -- tapping through angle1/angle2 without
     * actually rotating the piece, so two of the three saved photos are
     * near-duplicates of each other. PROVISIONAL threshold, not yet
     * calibrated against real "rotated vs not" examples -- tune
     * UNROTATED_MEAN_DIFF_THRESHOLD if it's too trigger-happy (flags a
     * real rotation as unmoved -- e.g. a small/symmetric item shifted
     * less than expected) or too lax (misses a genuine no-op retake).
     * Fails open (returns false, i.e. "looks fine") if either image
     * can't be decoded, since blocking a real capture on a decode glitch
     * is worse than missing a duplicate-angle check. */
    private fun looksUnrotated(a: ByteArray, b: ByteArray): Boolean {
        val gridSize = 24
        fun grayscaleGrid(bytes: ByteArray): IntArray? {
            // The result is reduced to a 24x24 luminance grid. Decoding a
            // 6K original at 1/8 scale wasted hundreds of milliseconds and
            // millions of pixels; 1/32 still gives far more than 24x24 input.
            val opts = BitmapFactory.Options().apply { inSampleSize = 32 }
            val decoded = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts) ?: return null
            val scaled = Bitmap.createScaledBitmap(decoded, gridSize, gridSize, true)
            val pixels = IntArray(gridSize * gridSize)
            scaled.getPixels(pixels, 0, gridSize, 0, 0, gridSize, gridSize)
            if (scaled !== decoded) scaled.recycle()
            decoded.recycle()
            return IntArray(pixels.size) { i ->
                val p = pixels[i]
                (((p shr 16) and 0xFF) + ((p shr 8) and 0xFF) + (p and 0xFF)) / 3
            }
        }
        val gridA = grayscaleGrid(a) ?: return false
        val gridB = grayscaleGrid(b) ?: return false
        var diffSum = 0L
        for (i in gridA.indices) diffSum += abs(gridA[i] - gridB[i])
        val meanDiff = diffSum.toDouble() / gridA.size
        Log.i(TAG, "looksUnrotated meanDiff=$meanDiff threshold=$UNROTATED_MEAN_DIFF_THRESHOLD")
        return meanDiff < UNROTATED_MEAN_DIFF_THRESHOLD
    }

    /** Gate an angle capture on looksUnrotated() -- if the new shot looks
     * like a near-duplicate of the previous angle, asks the operator to
     * actually move the item instead of silently accepting it. "Use
     * anyway" stays available for the rare legitimate case (a genuinely
     * symmetric piece that looks the same from multiple sides). */
    private fun promptRotateIfUnmoved(
        newBytes: ByteArray,
        previousBytes: ByteArray?,
        onConfirmed: () -> Unit,
        onRetake: () -> Unit
    ) {
        if (previousBytes == null) {
            onConfirmed()
            return
        }
        lifecycleScope.launch {
            val unmoved = withContext(Dispatchers.Default) {
                looksUnrotated(newBytes, previousBytes)
            }
            if (unmoved) {
                AlertDialog.Builder(this@MainActivity)
                    .setTitle("Item doesn't look moved")
                    .setMessage("This angle looks the same as the previous shot. Please turn/move the item, then retake.")
                    .setPositiveButton("Retake") { _, _ -> onRetake() }
                    .setNegativeButton("Use anyway") { _, _ -> onConfirmed() }
                    .setCancelable(false)
                    .show()
            } else {
                onConfirmed()
            }
        }
    }

    private fun captureAngle1() {
        if (angleCaptureInFlight) return
        angleCaptureInFlight = true
        setStatus("Capturing angle 1…", ready = false)
        angle1Validated = false
        angle1NeedsRetake = false
        // centerThenCapture() already completed touch-focus + stable-frame
        // gating. A second focus command here interrupted Sony Live View and
        // added delay immediately before every side shutter.
        captureFullRes(
            onShutterAccepted = {
                // Physical shutter has fired -- let the operator start
                // turning the item for angle 2 immediately instead of
                // waiting on the ~5s original download (2026-08-26,
                // explicit product decision). onAngle1Captured below runs
                // the not-moved check concurrently; fireAngle2WhenAngle1Ready()
                // is what actually gates angle 2's shutter on that result,
                // interrupting with a retake prompt if it comes back bad --
                // even if the operator has already started repositioning.
                promptForSideProfile("Turn the ornament to show the OTHER side profile, then tap READY") {
                    centerThenCapture { fireAngle2WhenAngle1Ready() }
                }
            }
        ) { bytes ->
            angleCaptureInFlight = false
            Log.i(TAG, "captureAngle1 result bytes=${bytes?.size}")
            onAngle1Captured(bytes)
        }
    }

    /** Gates angle 2's ACTUAL shutter (not the positioning prompt) on angle
     * 1's async not-moved check having resolved. Called once the operator
     * has repositioned, tapped READY, and centering/focus have settled --
     * by then angle 1's result has very likely already arrived, since a
     * human turning the item takes comparable or longer. */
    private fun fireAngle2WhenAngle1Ready() {
        if (angle1NeedsRetake) {
            angle1NeedsRetake = false
            promptForSideProfile("Angle 1 needs a retake — reposition, then tap READY") {
                centerThenCapture { captureAngle1() }
            }
            return
        }
        if (!angle1Validated) {
            setStatus("Confirming angle 1…", ready = false)
            handler.postDelayed({ fireAngle2WhenAngle1Ready() }, 150L)
            return
        }
        captureAngle2()
    }

    private fun onAngle1Captured(bytes: ByteArray?) {
        if (bytes == null) {
            angleCaptureRetryCount += 1
            if (angleCaptureRetryCount <= ANGLE_CAPTURE_MAX_RETRIES) {
                setStatus("Sony finishing previous transfer — retrying angle 1…", ready = false)
                handler.postDelayed({ captureAngle1() }, ANGLE_CAPTURE_RETRY_DELAY_MS)
            } else {
                Log.w(TAG, "Angle 1 capture unavailable after $angleCaptureRetryCount delayed attempts")
                // Unblock fireAngle2WhenAngle1Ready() if the operator already
                // reached that gate while this was still retrying. They may
                // already be mid-repositioning for angle 2 with nothing on
                // screen saying angle 1 failed -- surface it now rather than
                // silently waiting for them to hit the gate.
                Toast.makeText(this, "Angle 1 didn't save — you'll be asked to retake it", Toast.LENGTH_LONG).show()
                angle1NeedsRetake = true
                angle1Validated = true
            }
            return
        }
        angleCaptureRetryCount = 0
        // Item-not-moved check: angle1 should look visibly different from
        // MAIN (the item was supposed to be turned to show a side
        // profile) -- if it doesn't, the operator likely tapped through
        // READY without actually rotating the piece. Runs silently; only
        // interrupts (via fireAngle2WhenAngle1Ready's retake path) if it
        // actually finds a problem -- the happy path no longer blocks on a
        // manual preview here (2026-08-26, explicit product decision:
        // "start angle-2 positioning immediately, show review later if
        // needed" -- angle 1's full visual review was the thing waiting on
        // the ~5s download; the automated not-moved check is what actually
        // needs to gate the next shutter, not a human tapping Continue).
        promptRotateIfUnmoved(bytes, jewelJpeg, onConfirmed = {
            angle1Jpeg = bytes
            angle1Validated = true
        }, onRetake = {
            angle1NeedsRetake = true
            angle1Validated = true
        })
    }

    private fun captureAngle2() {
        if (angleCaptureInFlight) return
        angleCaptureInFlight = true
        setStatus("Capturing angle 2…", ready = false)
        captureFullRes { bytes ->
            angleCaptureInFlight = false
            Log.i(TAG, "captureAngle2 result bytes=${bytes?.size}")
            onAngle2Captured(bytes)
        }
    }

    private fun onAngle2Captured(bytes: ByteArray?) {
        if (bytes == null) {
            angleCaptureRetryCount += 1
            if (angleCaptureRetryCount <= ANGLE_CAPTURE_MAX_RETRIES) {
                setStatus("Sony finishing previous transfer — retrying angle 2…", ready = false)
                handler.postDelayed({ captureAngle2() }, ANGLE_CAPTURE_RETRY_DELAY_MS)
            } else {
                Log.w(TAG, "Angle 2 capture unavailable after $angleCaptureRetryCount delayed attempts")
                promptForSideProfile("Angle 2 not captured — reposition, then tap READY") {
                    centerThenCapture { captureAngle2() }
                }
            }
            return
        }
        angleCaptureRetryCount = 0
        // Same item-not-moved check as angle1, against angle1 this time --
        // angle2 is supposed to be the OTHER side profile.
        promptRotateIfUnmoved(bytes, angle1Jpeg, onConfirmed = {
            showCapturePreview(
                bytes,
                onProceed = {
                    angle2Jpeg = bytes
                    setStatus("Returning to center…", ready = false)
                    // Undoes the net tilt/pan correction accumulated across
                    // MAIN + angle1 + angle2's centering nudges in one shot, so
                    // the gimbal starts the next item from true center rather
                    // than wherever the last item's corrections left it.
                    // Tag was already scanned first under the #76 flip -- all
                    // 3 jewel shots are now done, upload instead of restarting.
                    undoCenteringThenAdvance {
                        inAngleSequence = false
                        uploadCapturedSet()
                    }
                },
                onRetake = { captureAngle2() },
                onCancel = { cancelItem() }
            )
        }, onRetake = { captureAngle2() })
    }

    private fun forceCaptureCurrentPhase() {
        when (phase) {
            Phase.JEWEL -> when {
                inAngleSequence && angle1Jpeg == null -> captureAngle1()
                inAngleSequence -> captureAngle2()
                else -> captureJewel()
            }
            Phase.TAG -> {
                if (SKIP_BARCODE_FOR_TESTING) {
                    // Temporary, per explicit request while testing the
                    // JEWEL flow -- bypasses the barcode scan entirely
                    // (which needs a real tag in frame every cycle) with a
                    // placeholder code + whatever's currently in frame as
                    // the "tag photo", then jumps straight to JEWEL. Set
                    // SKIP_BARCODE_FOR_TESTING back to false for real use.
                    captureTagFrame { bytes ->
                        tagJpeg = bytes
                        stableTagCode = "TEST-${System.currentTimeMillis()}"
                        resetForNewItem(Phase.JEWEL)
                        promptToPlaceMainItem()
                    }
                    return
                }
                captureTagFrame { bytes ->
                    if (bytes != null) {
                        tagJpeg = bytes
                        showCapturePreview(
                            bytes,
                            // Manual Capture on TAG is a staff override for a
                            // barcode that won't scan -- it takes a photo but
                            // was NEVER setting stableTagCode, since only the
                            // real scanner's success path does that. Confirmed
                            // live (2026-08-19): uploadMulti()/uploadPair()
                            // both hard-require a non-null tag code and
                            // silently discard the whole item otherwise
                            // ("Missing photo — retake", immediately
                            // overwritten by "Scanning tag…" on the next
                            // tick) -- two full items captured and lost with
                            // no visible error at all. Prompt for the code by
                            // hand here instead of leaving it null.
                            onProceed = { promptForManualTagCode() },
                            onRetake = { retakeTag() },
                            onCancel = { cancelItem() }
                        )
                    }
                }
            }
            Phase.UPLOADING -> {}
        }
    }

    /** TAG-phase Manual Capture never runs the real barcode scanner, so
     * stableTagCode is never set by that path -- ask the operator to type
     * the code by hand instead of silently proceeding with it null (see the
     * doc comment on the caller for the incident this closes). Blocks with
     * a non-cancelable dialog; blank/whitespace input keeps the dialog open
     * rather than letting the item continue untagged. */
    private fun promptForManualTagCode() {
        val input = EditText(this).apply {
            hint = "Tag code, e.g. WT22/128"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
        }
        val padding = (16 * resources.displayMetrics.density).toInt()
        val container = android.widget.FrameLayout(this).apply {
            setPadding(padding, padding, padding, padding)
            addView(input)
        }
        AlertDialog.Builder(this)
            .setTitle("Enter tag code")
            .setMessage("Barcode wasn't scanned for this item — type the tag code by hand.")
            .setView(container)
            .setCancelable(false)
            .setPositiveButton("Continue", null)
            .show()
            .apply {
                getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                    val code = input.text.toString().trim()
                    if (code.isEmpty()) {
                        input.error = "Required"
                        return@setOnClickListener
                    }
                    val continueButton = getButton(AlertDialog.BUTTON_POSITIVE)
                    continueButton.isEnabled = false
                    continueButton.text = "Checking…"
                    lifecycleScope.launch {
                        val result = UploadClient.resolveCategory(serverUrl(), code)
                        val category = result.category
                        if (category != null) {
                            stableTagCode = code
                            resolvedCategoryKey = category.key
                            categoryResolutionError = null
                            logCaptureEvent(
                                "manual_tag_code_entered",
                                mapOf("code" to code, "category" to category.key)
                            )
                            fetchStudFlagForCurrentTag(code)
                            dismiss()
                            resetForNewItem(Phase.JEWEL)
                            promptToPlaceMainItem()
                        } else {
                            input.error = if (result.serverReached) {
                                result.error ?: "Unknown stock label"
                            } else {
                                "Catalogue server unavailable — try again"
                            }
                            continueButton.isEnabled = true
                            continueButton.text = "Continue"
                        }
                    }
                }
            }
    }

    // ---------------------------------------------------------------- Capture preview

    /** Shows the just-captured photo full-screen with Retake/Cancel item
     * buttons and a short auto-continue countdown -- gives the operator a
     * real chance to catch a bad frame before it's used, matching
     * capture.html's own "Best frame selected · auto-proceeding in 3 sec"
     * preview step. */
    private fun showCapturePreview(
        jpeg: ByteArray,
        onProceed: () -> Unit,
        onComplete: (() -> Unit)? = null,
        onRetake: () -> Unit,
        onCancel: () -> Unit,
        requireManualConfirm: Boolean = false
    ) {
        val generation = ++previewGeneration
        previewShowing = true
        // Actually hide the live camera surface, not just draw over it --
        // a translucent overlay alone left the feed visibly bleeding
        // through underneath what was supposed to be a frozen photo.
        binding.previewView.visibility = View.INVISIBLE
        binding.sonyPreviewView.visibility = View.GONE
        binding.boundsOverlay.update(emptyList(), 0, 0, 0)
        // Reset any pinch-zoom/pan left over from inspecting the LAST
        // preview -- otherwise a new photo could open already zoomed in.
        binding.previewImage.scaleX = 1f
        binding.previewImage.scaleY = 1f
        binding.previewImage.translationX = 0f
        binding.previewImage.translationY = 0f
        binding.previewImage.setImageDrawable(null)
        binding.previewOverlay.visibility = View.VISIBLE
        previewCountdownRunnable?.let { handler.removeCallbacks(it) }
        previewCountdownRunnable = null
        binding.previewCountdown.text = "Preparing full-resolution preview…"
        binding.previewRetakeButton.isEnabled = false
        binding.previewContinueButton.isEnabled = false
        binding.previewCancelButton.isEnabled = false
        binding.previewCompleteButton.isEnabled = false
        binding.previewCompleteButton.visibility = if (onComplete == null) View.GONE else View.VISIBLE
        binding.previewContinueButton.text = if (onComplete == null) {
            getString(R.string.continue_now)
        } else {
            getString(R.string.proceed_angle_2)
        }

        // Decode only a display-sized derivative, off the UI thread. The
        // original JPEG byte array remains bit-for-bit untouched for upload.
        lifecycleScope.launch {
            val bitmap = withContext(Dispatchers.Default) { decodePreviewBitmap(jpeg) }
            if (generation != previewGeneration || !previewShowing || isDestroyed) {
                bitmap?.recycle()
                return@launch
            }
            if (bitmap == null) {
                Log.e(TAG, "Failed to decode captured JPEG for preview (${jpeg.size} bytes)")
                hideCapturePreview()
                onProceed()
                return@launch
            }
            capturePreviewBitmap?.recycle()
            capturePreviewBitmap = bitmap
            binding.previewImage.setImageBitmap(bitmap)

            binding.previewRetakeButton.isEnabled = true
            binding.previewContinueButton.isEnabled = true
            binding.previewCancelButton.isEnabled = true
            binding.previewCompleteButton.isEnabled = true
            binding.previewRetakeButton.setOnClickListener {
                hideCapturePreview()
                onRetake()
            }
            binding.previewContinueButton.setOnClickListener {
                hideCapturePreview()
                onProceed()
            }
            binding.previewCompleteButton.setOnClickListener {
                hideCapturePreview()
                onComplete?.invoke()
            }
            binding.previewCancelButton.setOnClickListener {
                hideCapturePreview()
                onCancel()
            }

            if (onComplete != null) {
                binding.previewCountdown.text = "Choose: capture more angles or complete this item"
            } else if (requireManualConfirm) {
                binding.previewCountdown.text = "Still soft after retries — tap Retake"
            } else {
                var secondsLeft = CAPTURE_PREVIEW_SECONDS
                val tick = object : Runnable {
                    override fun run() {
                        if (secondsLeft <= 0) {
                            hideCapturePreview()
                            onProceed()
                            return
                        }
                        binding.previewCountdown.text = "Continuing in ${secondsLeft}s… (pinch photo to zoom)"
                        secondsLeft -= 1
                        handler.postDelayed(this, 1000)
                    }
                }
                previewCountdownRunnable = tick
                handler.post(tick)
            }

            setupPreviewZoomAndPan()
        }
    }

    private fun decodePreviewBitmap(jpeg: ByteArray): Bitmap? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
        var sample = 1
        while (max(bounds.outWidth, bounds.outHeight) / sample > PREVIEW_DECODE_MAX_EDGE) {
            sample *= 2
        }
        return BitmapFactory.decodeByteArray(
            jpeg,
            0,
            jpeg.size,
            BitmapFactory.Options().apply { inSampleSize = sample }
        )
    }

    /** Every manual correction, logged as one JSON line -- the data-
     * collection tier of "can this learn from manual corrections" (2026-08-
     * 18, explicit request): no model, no training loop, just a durable
     * record of what staff actually did (category via the scanned tag,
     * before/after values, tap coordinates) so there's a real dataset to
     * calibrate against, or eventually train on, once there's volume.
     * Local-only (app-private external storage), append-only, fails silent
     * -- logging must never be able to interrupt a live capture. */
    private fun logManualAction(action: String, details: Map<String, Any?>) {
        try {
            val dir = getExternalFilesDir(null) ?: return
            val file = File(dir, "manual_corrections.jsonl")
            val entry = JSONObject().apply {
                put("ts", System.currentTimeMillis())
                put("action", action)
                put("tag", stableTagCode)
                put("phase", phase.name)
                details.forEach { (k, v) -> put(k, v) }
            }
            file.appendText(entry.toString() + "\n")
        } catch (e: Exception) {
            Log.w(TAG, "logManualAction($action) failed: ${e.message}")
        }
    }

    /** Durable record of every capture/upload outcome (2026-08-19, added
     * after 2 WATI items were captured in full auto mode but never landed
     * in capture_intake, with zero evidence to explain why -- logcat had
     * already rotated past it by the time it was noticed the next morning,
     * and every failure branch in uploadMulti/uploadPair only ever showed a
     * few-second Toast, easy to miss on an unattended run). Same
     * append-only, fail-silent JSONL convention as logManualAction, in a
     * SEPARATE file so a long unattended run's event history doesn't get
     * lost/rotated the way logcat did. Survives across app restarts, so the
     * next incident is a grep instead of a guess. */
    private fun logCaptureEvent(event: String, details: Map<String, Any?> = emptyMap()) {
        try {
            val dir = getExternalFilesDir(null) ?: return
            val file = File(dir, "capture_events.jsonl")
            val entry = JSONObject().apply {
                put("ts", System.currentTimeMillis())
                put("event", event)
                put("tag", stableTagCode)
                put("phase", phase.name)
                details.forEach { (k, v) -> put(k, v) }
            }
            file.appendText(entry.toString() + "\n")
        } catch (e: Exception) {
            Log.w(TAG, "logCaptureEvent($event) failed: ${e.message}")
        }
    }

    /** Same reasoning as showItemSavedPopup: a failure Toast disappears in a
     * couple seconds and is trivial to miss with hands full of jewellery, or
     * on an unattended auto-mode run -- which is exactly how 2 real items
     * went missing with no visible trace (2026-08-19). Every upload failure
     * path now blocks on an explicit acknowledgment instead, and is always
     * paired with a logCaptureEvent call so it's also in capture_events.jsonl
     * even if nobody was there to see the dialog. */
    private fun showUploadFailedPopup(reason: String) {
        AlertDialog.Builder(this)
            .setTitle("Save failed")
            .setMessage(reason)
            .setCancelable(false)
            .setPositiveButton("OK") { _, _ -> resetForNewItem(Phase.TAG) }
            .show()
    }

    /** Wires zoom +/-, exposure, and focus controls. Only zoom +/- engages
     * manual mode. Exposure and focus remain compatible with AUTO. */
    // ---------------------------------------------------------------- Camera-source compatibility

    private fun cameraZoomRatio(): Float =
        if (activeCameraSource == ProductionCameraSource.SONY) sonyZoomRatio
        else focusZoom.currentZoomRatio()

    private fun cameraZoomRange(): ClosedFloatingPointRange<Float> =
        if (activeCameraSource == ProductionCameraSource.SONY) {
            SONY_MIN_ZOOM_RATIO..SONY_MAX_ZOOM_RATIO
        } else focusZoom.zoomRatioRange()

    private fun setCameraZoomRatio(requested: Float, onResult: (Boolean) -> Unit = {}) {
        if (activeCameraSource != ProductionCameraSource.SONY) {
            focusZoom.setZoomRatio(requested)
            onResult(true)
            return
        }
        val target = requested.coerceIn(SONY_MIN_ZOOM_RATIO, SONY_MAX_ZOOM_RATIO)
        // Do not blend a pre-zoom distance estimate with the new field of
        // view. The next analysed frame establishes a fresh ratio.
        standDistanceRatioEma = null
        val before = sonyProduction.currentZoomRatio()
        sonyZoomRatio = before
        sonyZoomTarget = before
        val delta = target - before
        if (abs(delta) < 0.015f) {
            onResult(true)
            return
        }
        val tele = delta > 0f
        val hardTeleEndpoint = tele && target >= SONY_MAX_ZOOM_RATIO - 0.01f
        val holdMs = if (hardTeleEndpoint) {
            SONY_ZOOM_WIDE_ENDPOINT_HOLD_MS
        } else {
            (abs(delta) /
                (SONY_MAX_ZOOM_RATIO - SONY_MIN_ZOOM_RATIO) * SONY_ZOOM_FULL_TRAVEL_MS)
                .toLong().coerceIn(80L, 1_800L)
        }
        lastZoomChangeAt = System.currentTimeMillis()
        sonyProduction.driveZoom(tele, holdMs) { ok ->
            if (ok) {
                sonyZoomRatio = if (hardTeleEndpoint) {
                    SONY_MAX_ZOOM_RATIO
                } else {
                    sonyProduction.currentZoomRatio()
                }
            }
            sonyZoomTarget = sonyZoomRatio
            Log.i(
                TAG,
                "Sony physical AUTO zoom tele=$tele holdMs=$holdMs before=$before " +
                    "requested=$target confirmed=$sonyZoomRatio ok=$ok"
            )
            onResult(ok)
        }
    }

    private fun updateCameraTrackingRegion(cx: Float, cy: Float) {
        if (activeCameraSource == ProductionCameraSource.PHONE) {
            focusZoom.updateTrackingRegion(cx, cy)
        }
        // Sony's current PTP surface exposes autofocus but not a verified
        // movable AF-area property. Existing gimbal centering puts the
        // deterministic gold target under the camera's central AF area.
    }

    private fun startCameraContinuousTracking() {
        if (activeCameraSource == ProductionCameraSource.SONY) triggerCameraAutoFocus()
        else focusZoom.startContinuousTracking()
    }

    @Suppress("UNUSED_PARAMETER")
    private fun triggerCameraAutoFocus(
        physicalSony: Boolean = false,
        normalizedX: Float? = null,
        normalizedY: Float? = null,
        manualRequest: Boolean = false
    ): Boolean {
        if (activeCameraSource != ProductionCameraSource.SONY) {
            focusZoom.triggerAutoFocus()
            return true
        }
        // AF-C/Pre-AF remains the non-disruptive baseline. A decisive focus
        // gate explicitly requests physicalSony=true once per zoom level.
        if (!physicalSony) return false
        val now = System.currentTimeMillis()
        if (now - sonyAfRequestedAt < 650L) return false
        if (!manualRequest &&
            sonyAutomaticAfCommandsForPose >= MAX_AUTOMATIC_AF_COMMANDS_PER_POSE
        ) {
            Log.w(
                TAG,
                "Sony automatic AF suppressed: pose budget=" +
                    "$sonyAutomaticAfCommandsForPose/$MAX_AUTOMATIC_AF_COMMANDS_PER_POSE"
            )
            return false
        }
        if (!manualRequest) sonyAutomaticAfCommandsForPose += 1
        sonyAfRequestedAt = now
        sonyAfRequestedAtNanos = System.nanoTime()
        sonyAfCommandAcknowledged = false
        // Use Creators' App's SDI-310 RemoteTouchOperation on the existing
        // PTP session. Automatic and manual decisive requests both use the
        // camera's real AF motor and the detected/tapped point.
        val bounds = latestMaterial?.bounds
        val focusX = normalizedX?.coerceIn(0f, 1f)
            ?: bounds?.let { (it.x0 + it.x1) * 0.5f } ?: 0.5f
        val focusY = normalizedY?.coerceIn(0f, 1f)
            ?: bounds?.let { (it.y0 + it.y1) * 0.5f } ?: 0.5f
        sonyFocusX = focusX
        sonyFocusY = focusY
        binding.boundsOverlay.updateCameraFocus(
            sonyFocusX,
            sonyFocusY,
            sonyProduction.currentFocusSnapshot()?.indication
        )
        Log.i(
            TAG,
            "Sony AF request x=$focusX y=$focusY manual=$manualRequest " +
                "poseCount=$sonyAutomaticAfCommandsForPose"
        )
        sonyProduction.autofocus(
            normalizedX = focusX,
            normalizedY = focusY
        ) { ok ->
            sonyAfCommandAcknowledged = ok
            if (ok) {
                // Reject a green AF status belonging to the frame that
                // existed before this exact touch-focus command.
                sonyAfRequestedAtNanos = System.nanoTime()
            }
        }
        return true
    }

    /** One-way optical focus ladder. Every failed magnification becomes the
     * new ceiling; no path can immediately climb back and repeat it. */
    private fun backOffOneZoomForFocus(onDone: (() -> Unit)? = null): Boolean {
        val zoom = cameraZoomRatio()
        val floor = cameraZoomRange().start
        if (zoom <= floor + 0.03f) return false
        val next = (zoom / ZOOM_STEP_RATIO).coerceAtLeast(floor)
        if (next >= zoom - 0.01f) return false
        maxUsableZoom = min(maxUsableZoom, next)
        stepFocusAttempts += 1
        focusTriggeredThisLevel = false
        focusEvaluationNotBefore = 0L
        focusEvaluationNotBefore = 0L
        sonyAfRequestedAt = 0L
        sonyAfRequestedAtNanos = 0L
        sonyAfCommandAcknowledged = false
        readyStreak = 0
        Log.i(
            TAG,
            "Focus ladder backoff level=$stepFocusAttempts from=$zoom to=$next " +
                "sharpness=$latestSharpness ceiling=$maxUsableZoom"
        )
        setStatus("Image soft — zooming back one step and refocusing…", ready = false)
        smoothZoomTo(next, onDone = onDone)
        return true
    }

    private fun resetSonyAutomaticAfBudget() {
        sonyAutomaticAfCommandsForPose = 0
        focusEvaluationNotBefore = 0L
        sonyAfRequestedAt = 0L
        sonyAfRequestedAtNanos = 0L
        sonyAfCommandAcknowledged = false
    }

    private fun cameraAfState(): Int? {
        if (activeCameraSource != ProductionCameraSource.SONY) return focusZoom.afState.value
        val snapshot = sonyProduction.currentFocusSnapshot()
        val isFreshForRequest = sonyAfRequestedAtNanos == 0L ||
            (snapshot != null && snapshot.receivedAtNanos > sonyAfRequestedAtNanos)
        when (snapshot?.indication) {
            // Camera-native AF state is primary. The separate multi-frame
            // detail gate remains a sanity check before shutter; it no
            // longer rewrites a real Sony focus lock into a software guess.
            2, 6 -> if (isFreshForRequest) {
                return CaptureResult.CONTROL_AF_STATE_FOCUSED_LOCKED
            }
            3, 7 -> return CaptureResult.CONTROL_AF_STATE_NOT_FOCUSED_LOCKED
            5 -> return CaptureResult.CONTROL_AF_STATE_ACTIVE_SCAN
        }
        if (sonyAfRequestedAt == 0L) return CaptureResult.CONTROL_AF_STATE_PASSIVE_SCAN
        val elapsed = System.currentTimeMillis() - sonyAfRequestedAt
        if (elapsed < 700L) return CaptureResult.CONTROL_AF_STATE_ACTIVE_SCAN
        // Sony does not publish Camera2 AF state over this PTP session.
        // Command ACK plus fresh ROI detail is the equivalent production
        // lock gate; if the body omits an ACK, sharpness still fails closed.
        return if (elapsed >= 1_500L) {
            CaptureResult.CONTROL_AF_STATE_NOT_FOCUSED_LOCKED
        } else CaptureResult.CONTROL_AF_STATE_ACTIVE_SCAN
    }

    private fun isCameraFocusLocked(state: Int?): Boolean =
        if (activeCameraSource == ProductionCameraSource.SONY) {
            state == CaptureResult.CONTROL_AF_STATE_FOCUSED_LOCKED ||
                // Some ZV-E10 II AF-C sessions remain in camera state 5
                // (tracking) instead of publishing state 6 for a stationary
                // remote-touch target. Accept this for capture only when the
                // command was acknowledged, focal metadata is fresh, and the
                // separate multi-frame detail gate passes. The UI continues
                // to display the raw Sony state; this is not fake telemetry.
                (state == CaptureResult.CONTROL_AF_STATE_ACTIVE_SCAN &&
                    sonyAfCommandAcknowledged &&
                    sonyProduction.currentFocusSnapshot()?.receivedAtNanos
                        ?.let { it > sonyAfRequestedAtNanos } == true &&
                    latestSharpness >= SHARPNESS_THRESHOLD)
        } else focusZoom.isFocusLocked(state)

    private fun isCameraFocusFailed(state: Int?): Boolean =
        if (activeCameraSource == ProductionCameraSource.SONY) {
            state == CaptureResult.CONTROL_AF_STATE_NOT_FOCUSED_LOCKED
        } else focusZoom.isFocusFailed(state)

    private fun cameraExposureControlAvailable(): Boolean =
        if (activeCameraSource == ProductionCameraSource.SONY) sonyProduction.isAvailable
        else focusZoom.exposureControlAvailable()

    private fun cameraExposureRangeEv(): ClosedFloatingPointRange<Float> =
        if (activeCameraSource == ProductionCameraSource.SONY) {
            SONY_MIN_EXPOSURE_EV..SONY_MAX_EXPOSURE_EV
        } else focusZoom.exposureCompensationRangeEv()

    private fun setCameraExposureCompensationEv(ev: Float) {
        if (activeCameraSource == ProductionCameraSource.SONY) {
            sonyProduction.setExposureCompensationEv(
                ev.coerceIn(SONY_MIN_EXPOSURE_EV, SONY_MAX_EXPOSURE_EV)
            )
        } else focusZoom.setExposureCompensationEv(ev)
    }

    private fun driveSonyManualZoom(tele: Boolean) {
        // Conflate rapid taps into a bounded latest-direction queue. This
        // prevents overlapping Sony transactions while retaining up to three
        // intentional taps; tapping the opposite direction cancels backlog.
        sonyManualZoomPendingSteps = (sonyManualZoomPendingSteps + if (tele) 1 else -1)
            .coerceIn(-SONY_MANUAL_ZOOM_MAX_QUEUED_STEPS, SONY_MANUAL_ZOOM_MAX_QUEUED_STEPS)
        drainSonyManualZoomQueue()
    }

    private fun drainSonyManualZoomQueue() {
        if (sonyManualZoomInFlight || sonyManualZoomPendingSteps == 0 ||
            activeCameraSource != ProductionCameraSource.SONY
        ) return
        val tele = sonyManualZoomPendingSteps > 0
        sonyManualZoomPendingSteps += if (tele) -1 else 1
        sonyManualZoomInFlight = true
        val before = sonyProduction.currentZoomRatio()
        lastZoomChangeAt = System.currentTimeMillis()
        sonyProduction.driveZoom(tele, SONY_MANUAL_ZOOM_PULSE_MS) { ok ->
            if (ok) sonyZoomRatio = sonyProduction.currentZoomRatio()
            sonyZoomTarget = sonyZoomRatio
            sonyManualZoomInFlight = false
            logManualAction(
                if (tele) "zoom_in" else "zoom_out",
                mapOf("from" to before, "to" to sonyZoomRatio, "motor" to true, "ok" to ok)
            )
            if (ok) {
                sonyManualZoomBusyRetries = 0
                drainSonyManualZoomQueue()
            } else if (sonyProduction.isAvailable &&
                sonyManualZoomBusyRetries < SONY_MANUAL_ZOOM_BUSY_RETRIES
            ) {
                sonyManualZoomBusyRetries += 1
                sonyManualZoomPendingSteps = (sonyManualZoomPendingSteps + if (tele) 1 else -1)
                    .coerceIn(
                        -SONY_MANUAL_ZOOM_MAX_QUEUED_STEPS,
                        SONY_MANUAL_ZOOM_MAX_QUEUED_STEPS
                    )
                handler.postDelayed(::drainSonyManualZoomQueue, 60L)
            } else {
                sonyManualZoomBusyRetries = 0
                Log.w(TAG, "Sony manual zoom failed tele=$tele before=$before")
            }
        }
    }

    private fun setupManualControls() {
        binding.zoomInButton.setOnClickListener {
            engageManual()
            if (activeCameraSource == ProductionCameraSource.SONY) {
                driveSonyManualZoom(tele = true)
                return@setOnClickListener
            }
            val range = cameraZoomRange()
            val before = cameraZoomRatio()
            val next = (before * 1.15f).coerceIn(range.start, min(range.endInclusive, MAX_LIVE_ZOOM_RATIO))
            setCameraZoomRatio(next)
            logManualAction("zoom_in", mapOf("from" to before, "to" to next))
        }
        binding.zoomOutButton.setOnClickListener {
            engageManual()
            if (activeCameraSource == ProductionCameraSource.SONY) {
                driveSonyManualZoom(tele = false)
                return@setOnClickListener
            }
            val range = cameraZoomRange()
            val before = cameraZoomRatio()
            val next = (before / 1.15f).coerceIn(range.start, min(range.endInclusive, MAX_LIVE_ZOOM_RATIO))
            setCameraZoomRatio(next)
            logManualAction("zoom_out", mapOf("from" to before, "to" to next))
        }

        binding.resumeAutoButton.setOnClickListener {
            manualModeActive = false
            manualFocusLocked = false
            binding.manualModeText.text = getString(R.string.auto_tracking)
            binding.resumeAutoButton.visibility = View.GONE
            startCameraContinuousTracking()
            logManualAction("resume_auto", emptyMap())
        }

        // Tap-to-focus / long-press-to-lock. Coordinates approximated as a
        // fraction of previewView's own width/height -- this app runs the
        // preview full-bleed (match_parent, no letterboxing crop applied
        // in layout), so tap-fraction and camera-frame-fraction track
        // closely enough for a metering region without needing CameraX's
        // separate MeteringPointFactory machinery.
        val gestureDetector = GestureDetector(this, object : GestureDetector.SimpleOnGestureListener() {
            override fun onSingleTapUp(e: MotionEvent): Boolean {
                val (cx, cy) = normalizedPreviewTouch(e)
                manualFocusLocked = false
                updateCameraTrackingRegion(cx, cy)
                triggerCameraAutoFocus(
                    physicalSony = true,
                    normalizedX = cx,
                    normalizedY = cy,
                    manualRequest = true
                )
                logManualAction("tap_focus", mapOf("cx" to cx, "cy" to cy))
                return true
            }
            override fun onLongPress(e: MotionEvent) {
                val (cx, cy) = normalizedPreviewTouch(e)
                updateCameraTrackingRegion(cx, cy)
                triggerCameraAutoFocus(
                    physicalSony = true,
                    normalizedX = cx,
                    normalizedY = cy,
                    manualRequest = true
                )
                manualFocusLocked = true
                logManualAction("focus_lock", mapOf("cx" to cx, "cy" to cy))
            }
        })
        val previewTouchListener = View.OnTouchListener { _, event ->
            gestureDetector.onTouchEvent(event)
            true
        }
        binding.previewView.setOnTouchListener(previewTouchListener)
        binding.sonyPreviewView.setOnTouchListener(previewTouchListener)
    }

    /** Map taps through Sony ImageView FIT_CENTER letterboxing. */
    private fun normalizedPreviewTouch(event: MotionEvent): Pair<Float, Float> {
        if (activeCameraSource != ProductionCameraSource.SONY) {
            return Pair(
                (event.x / binding.previewView.width.coerceAtLeast(1)).coerceIn(0f, 1f),
                (event.y / binding.previewView.height.coerceAtLeast(1)).coerceIn(0f, 1f)
            )
        }
        val viewWidth = binding.sonyPreviewView.width.coerceAtLeast(1).toFloat()
        val viewHeight = binding.sonyPreviewView.height.coerceAtLeast(1).toFloat()
        val bitmap = latestSonyPreviewBitmap
        if (bitmap == null || bitmap.width <= 0 || bitmap.height <= 0) {
            return Pair((event.x / viewWidth).coerceIn(0f, 1f), (event.y / viewHeight).coerceIn(0f, 1f))
        }
        val scale = min(viewWidth / bitmap.width, viewHeight / bitmap.height)
        val renderedWidth = bitmap.width * scale
        val renderedHeight = bitmap.height * scale
        val left = (viewWidth - renderedWidth) * 0.5f
        val top = (viewHeight - renderedHeight) * 0.5f
        return Pair(
            ((event.x - left) / renderedWidth).coerceIn(0f, 1f),
            ((event.y - top) / renderedHeight).coerceIn(0f, 1f)
        )
    }

    /** Enter the explicit manual-zoom override. Called only by zoom +/-. */
    private fun engageManual() {
        if (!manualModeActive) {
            manualModeActive = true
            binding.manualModeText.text = getString(R.string.manual_mode)
            binding.resumeAutoButton.visibility = View.VISIBLE
        }
    }

    /** Wires the exposure slider to the camera's REAL EV range/step --
     * must run AFTER focusZoom.bind() has actually read
     * CameraCharacteristics, not from onCreate. Confirmed live (2026-08-
     * 18): calling this too early made exposureControlAvailable() read
     * false (nothing bound yet) and permanently hid the slider row, even
     * though the hardware genuinely supports EV compensation. Called once
     * per camera bind from startCamera(), right after focusZoom.bind(). */
    private fun configureExposureSlider() {
        if (!cameraExposureControlAvailable()) {
            binding.exposureRow.visibility = View.GONE
            return
        }
        binding.exposureRow.visibility = View.VISIBLE
        val evRange = cameraExposureRangeEv()
        val sliderStepsPerEv = if (activeCameraSource == ProductionCameraSource.SONY) 3f else 10f
        val span = ((evRange.endInclusive - evRange.start) * sliderStepsPerEv)
            .roundToInt().coerceAtLeast(1)
        binding.exposureSeekBar.max = span
        binding.exposureSeekBar.progress =
            ((autoExposureEv - evRange.start) * sliderStepsPerEv).roundToInt().coerceIn(0, span)
        binding.exposureSeekBar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            private var beforeDrag = autoExposureEv
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                if (!fromUser) return
                val ev = evRange.start + progress / sliderStepsPerEv
                autoExposureEv = ev
                // CameraX can accept continuous slider updates. Sony cannot:
                // each property write briefly releases HTTP Live View. Send
                // only the final Sony value when the finger lifts.
                if (activeCameraSource != ProductionCameraSource.SONY) {
                    setCameraExposureCompensationEv(ev)
                }
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {
                beforeDrag = autoExposureEv
                manualExposureOverride = true
                pendingAutoExposureEv = null
                exposureClipStreak = 0
                exposureClearStreak = 0
            }
            override fun onStopTrackingTouch(seekBar: SeekBar?) {
                if (activeCameraSource == ProductionCameraSource.SONY) {
                    setCameraExposureCompensationEv(autoExposureEv)
                }
                logManualAction("exposure", mapOf("from" to beforeDrag, "to" to autoExposureEv))
            }
        })
    }

    /**
     * Pinch-to-zoom + one-finger pan on the just-captured photo so the
     * operator can actually verify fine detail before accepting a shot,
     * plus the fix for the countdown not "sticking": touching the image to
     * zoom used to do nothing to the 5s auto-continue timer running
     * underneath, so it could fire and dismiss the photo out from under an
     * operator mid-inspection. Any touch here now cancels that timer for
     * good -- Retake/Continue/Cancel become the only way forward, which is
     * also why Continue exists as its own button now instead of relying on
     * the countdown as the sole "yes, use this" action.
     */
    private fun setupPreviewZoomAndPan() {
        val image = binding.previewImage
        val scaleDetector = ScaleGestureDetector(this, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            override fun onScale(detector: ScaleGestureDetector): Boolean {
                val newScale = (image.scaleX * detector.scaleFactor).coerceIn(1f, 6f)
                image.scaleX = newScale
                image.scaleY = newScale
                return true
            }
        })
        var lastX = 0f
        var lastY = 0f
        image.setOnTouchListener { _, event ->
            scaleDetector.onTouchEvent(event)
            previewCountdownRunnable?.let { handler.removeCallbacks(it) }
            previewCountdownRunnable = null
            binding.previewCountdown.text = "Pinch to zoom · tap Continue when done"
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    lastX = event.rawX
                    lastY = event.rawY
                }
                MotionEvent.ACTION_MOVE -> {
                    if (event.pointerCount == 1 && image.scaleX > 1.01f) {
                        image.translationX += event.rawX - lastX
                        image.translationY += event.rawY - lastY
                    }
                    lastX = event.rawX
                    lastY = event.rawY
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    if (image.scaleX <= 1.01f) {
                        image.translationX = 0f
                        image.translationY = 0f
                    }
                }
            }
            true
        }
    }

    private fun hideCapturePreview() {
        previewGeneration += 1L
        previewCountdownRunnable?.let { handler.removeCallbacks(it) }
        previewCountdownRunnable = null
        binding.previewImage.setImageDrawable(null)
        capturePreviewBitmap?.recycle()
        capturePreviewBitmap = null
        binding.previewOverlay.visibility = View.GONE
        binding.previewView.visibility = if (activeCameraSource == ProductionCameraSource.SONY) {
            View.GONE
        } else {
            View.VISIBLE
        }
        binding.sonyPreviewView.visibility = if (activeCameraSource == ProductionCameraSource.SONY) {
            View.VISIBLE
        } else {
            View.GONE
        }
        previewShowing = false
    }

    /** Discards the jewel shot and re-arms the JEWEL pipeline from
     * scratch, staying in this session (not returning to the browser). */
    private fun retakeJewel() {
        jewelJpeg = null
        angle1Jpeg = null; angle1Validated = false; angle1NeedsRetake = false
        angle2Jpeg = null
        inAngleSequence = false
        angleCaptureInFlight = false
        angleCaptureRetryCount = 0
        angleFocusTriggered = false
        hideReadyButton()
        armed = false
        stepFocusAttempts = 0
        resetSonyAutomaticAfBudget()
        maxUsableZoom = Float.MAX_VALUE
        maxUsableZoomStuckSince = 0L
        latestMaterial = null
        autoFired = false
        armedAt = System.currentTimeMillis()
        lastZoomChangeAt = 0L
        focusTriggeredThisLevel = false
        focusEvaluationNotBefore = 0L
        isZooming = false
        stallGraceAt = 0L
        tooCloseWarned = false
        readyStreak = 0
        jewelCaptureRetries = 0
        // Defensive only -- a retake mid-centering/mid-angle-sequence means
        // the gimbal may be physically left wherever those nudges put it
        // (no undo fires on this path), but at least the NEXT item's
        // bookkeeping starts clean instead of compounding stale ticks.
        centeringPanMs = 0
        centeringTiltMs = 0
        centeringAttempts = 0
        angleZoomRounds = 0
        lastCenterAxis = CenterAxis.NONE
        centerAvoidAxis = CenterAxis.NONE
        lockedBoxCenter = null
        huntPhase = HuntPhase.SCAN_DOWN
        huntPhaseMsSpent = 0
        huntStartedAt = 0L
        latestObjectBoxesUpright = emptyList()
        setCameraZoomRatio(1f)
        setStatus("Center the ornament, front side up…", ready = false)
    }

    /** Discards the tag shot only -- the jewel shot already captured
     * stays, no need to redo it. */
    private fun retakeTag() {
        tagJpeg = null
        resetSonyTagBurst()
        tagCodeHistory = mutableListOf()
        stableTagCode = null
        resolvedCategoryKey = null
        categoryResolutionCode = null
        categoryResolutionError = null
        invalidTagCode = null
        studFlagPersisted = null
        studAutoGuess = false
        wrongShapeSince = 0L
        aiShapeAdviceCategory = null
        aiShapeOverrideUntil = 0L
        updateStudStatusUi()
        autoFired = false
        barcodeAttempts = 0
        lastBarcodeCount = -1
        lastBarcodeError = null
        setStatus("Show the tag QR/barcode…", ready = false)
    }

    /** Abandons the item entirely (no upload). If this session was handed
     * off from the browser, return to it immediately -- same reasoning as
     * finishOrResetForNewItem: the browser is the anchor, this app's job
     * for this item is simply over. Otherwise loop for a fresh item. */
    private fun cancelItem() {
        inAngleSequence = false
        angleCaptureInFlight = false
        angleCaptureRetryCount = 0
        hideReadyButton()
        rsc2.stopAndReturnToCenter()
        if (launchedFromBrowser) {
            finish()
        } else {
            // Abandoning the item entirely -- next cycle starts from a
            // fresh tag scan, not jewel capture (see #76 flip).
            resetForNewItem(Phase.TAG)
        }
    }

    /** Takes exactly one still and returns its bytes, or null on failure.
     * [onShutterAccepted] fires the instant the physical shutter is
     * confirmed -- well before [onResult]'s full original download -- so a
     * caller can let the operator start the NEXT physical step immediately
     * instead of waiting on transfer. Defaults to a no-op for callers that
     * don't need the earlier signal. */
    private fun captureOneFrame(
        source: ProductionCameraSource = activeCameraSource,
        onShutterAccepted: () -> Unit = {},
        onResult: (ByteArray?) -> Unit
    ) {
        if (source == ProductionCameraSource.SONY) {
            sonyProduction.captureStill(onShutterAccepted = onShutterAccepted, onResult = onResult)
            return
        }
        // CameraX's ImageCapture API doesn't expose a separate shutter-
        // accepted signal ahead of onCaptureSuccess; firing it here (capture
        // actually requested) is the closest available equivalent.
        onShutterAccepted()
        val capture = imageCapture ?: run { onResult(null); return }
        capture.takePicture(
            ContextCompat.getMainExecutor(this),
            object : ImageCapture.OnImageCapturedCallback() {
                override fun onCaptureSuccess(image: ImageProxy) {
                    val bytes = jpegBytesFrom(image)
                    image.close()
                    onResult(bytes)
                }

                override fun onError(exception: ImageCaptureException) {
                    Log.e(TAG, "Capture failed", exception)
                    // A dead/unbound camera session ("Camera is not active"
                    // -- CameraControl$OperationCanceledException) does not
                    // recover on its own: every retry keeps hitting the same
                    // dead session forever, which is how an item could fail
                    // to save with zero path to succeed. Same fix as the
                    // onResume() rebind for navigating away and back: rebind
                    // the use cases so the NEXT attempt has a live session.
                    // Cooldown so a genuinely one-off transient error doesn't
                    // trigger a rebind storm.
                    val now = System.currentTimeMillis()
                    if (now - lastCameraRebindAt > 3000L && ::cameraProvider.isInitialized) {
                        lastCameraRebindAt = now
                        Log.w(TAG, "Rebinding camera use cases after capture failure")
                        bindUseCases()
                    }
                    onResult(null)
                }
            }
        )
    }

    /** One physical shutter per requested view. The old two-frame sharpness
     * burst doubled all three shutters and added roughly 25-30 seconds per
     * item. Focus and motion quality are already gated before this call. */
    private fun captureFullRes(onShutterAccepted: () -> Unit = {}, onResult: (ByteArray?) -> Unit) {
        // One physical shutter per requested view. Focus-state, stable-frame
        // and gimbal-still gates have already passed before this call.
        val captureSource = activeCameraSource
        val captureEpoch = cameraModeEpoch
        captureOneFrame(captureSource, onShutterAccepted = onShutterAccepted) frame@{ bytes ->
            if (captureEpoch != cameraModeEpoch || captureSource != activeCameraSource) {
                Log.w(TAG, "Discarding frame after camera-mode change")
                onResult(null)
                return@frame
            }
            onResult(bytes)
        }
    }

    private fun jpegBytesFrom(image: ImageProxy): ByteArray {
        val buffer: ByteBuffer = image.planes[0].buffer
        val bytes = ByteArray(buffer.remaining())
        buffer.get(bytes)
        return bytes
    }

    /** Dispatches to the 3-angle upload when the RSC 2 sequence produced
     * angle1/angle2 shots, otherwise the original single-image path --
     * called from both the auto-fire and manual-shutter TAG capture sites. */
    private fun uploadCapturedSet() {
        // All camera captures are complete. Reset the physical lens NOW,
        // in parallel with local staging/upload, so the next tag is already
        // presented at true 16mm/full-wide. Do not wait for the background
        // upload or the next-item screen transition.
        resetSonyZoomFullyWideForNextTag()
        if (angle1Jpeg != null && angle2Jpeg != null) uploadMulti() else uploadPair()
    }

    private var wideResetInFlight = false
    private var wideResetComplete = false
    private var wideResetAttempts = 0

    /** Hard endpoint reset. A normal ratio command uses the controller's
     * estimated position and can inherit motor-timing drift. Holding WIDE
     * beyond measured full travel guarantees the lens reaches its own 16mm
     * stop. Failed/busy PTP commands retry without blocking local staging. */
    private fun resetSonyZoomFullyWideForNextTag() {
        if (activeCameraSource != ProductionCameraSource.SONY) {
            setCameraZoomRatio(SONY_MIN_ZOOM_RATIO)
            return
        }
        if (wideResetInFlight || wideResetComplete) return
        if (!sonyProduction.isAvailable) {
            Log.i(TAG, "Sony next-item full-wide reset deferred until camera ready")
            return
        }
        sonyManualZoomPendingSteps = 0
        wideResetInFlight = true
        wideResetAttempts += 1
        val attempt = wideResetAttempts
        Log.i(TAG, "Sony next-item full-wide reset start attempt=$attempt")
        sonyProduction.driveZoom(
            tele = false,
            durationMs = SONY_ZOOM_WIDE_ENDPOINT_HOLD_MS
        ) { ok ->
            wideResetInFlight = false
            sonyZoomRatio = sonyProduction.currentZoomRatio()
            sonyZoomTarget = sonyZoomRatio
            if (ok) {
                wideResetComplete = true
                wideResetAttempts = 0
                Log.i(TAG, "Sony next-item full-wide reset complete ratio=$sonyZoomRatio")
            } else if (wideResetAttempts < SONY_ZOOM_WIDE_RESET_MAX_ATTEMPTS &&
                !isDestroyed
            ) {
                Log.w(TAG, "Sony next-item full-wide reset busy/failed attempt=$attempt; retrying")
                handler.postDelayed(::resetSonyZoomFullyWideForNextTag, 400L)
            } else {
                Log.e(TAG, "Sony next-item full-wide reset failed after $attempt attempts")
            }
        }
    }

    private fun uploadMulti() {
        val main = jewelJpeg
        val angle1 = angle1Jpeg
        val angle2 = angle2Jpeg
        val tagCode = stableTagCode
        if (main == null || angle1 == null || angle2 == null || tagCode == null) {
            logCaptureEvent("upload_multi_missing_field", mapOf(
                "main" to (main != null), "angle1" to (angle1 != null),
                "angle2" to (angle2 != null), "tagCode" to (tagCode != null)
            ))
            showUploadFailedPopup("Missing photo or tag — please retake this item.")
            return
        }
        phase = Phase.UPLOADING
        setStatus("Securing 3-angle set locally…", ready = false)
        logCaptureEvent("upload_multi_stage_attempt")
        val serverUrl = serverUrl()
        val staffName = prefs.getString("staff_name", "") ?: ""
        if (serverUrl.isBlank()) {
            logCaptureEvent("upload_blocked_no_server_url")
            Toast.makeText(this, "Set the capture server URL in Settings first", Toast.LENGTH_LONG).show()
            showSettingsDialog()
            resetForNewItem(Phase.TAG)
            return
        }
        lifecycleScope.launch {
            val staged = try {
                CaptureUploadQueue.stageMulti(
                    applicationContext, serverUrl, tagCode, staffName,
                    main, angle1, angle2
                )
            } catch (e: Exception) {
                Log.e(TAG, "Multi-angle local staging failed", e)
                logCaptureEvent("upload_multi_stage_failed", mapOf("message" to e.message))
                showUploadFailedPopup("Could not secure photos locally: ${e.message}")
                return@launch
            }
            logCaptureEvent("upload_multi_queued", mapOf("job_id" to staged.id))
            jewelJpeg = null
            angle1Jpeg = null; angle1Validated = false; angle1NeedsRetake = false
            angle2Jpeg = null
            tagJpeg = null
            Toast.makeText(this@MainActivity, "Queued $tagCode — uploading in background", Toast.LENGTH_SHORT).show()
            finishOrResetForNewItem()
        }
    }

    /** One override at a time (e.g. duplicate) does not guarantee the NEXT
     * gate passes -- confirmed live (2026-08-19, tag BL18/2): duplicate
     * override accepted, then the server's separate visibility check
     * rejected the same retry, and this function used to treat that as a
     * flat dead-end failure ("Save failed: not_clearly_visible") with no
     * way to override it, forcing a full retake even though the operator
     * had already cleared one warning. Chains through the same
     * confirm-and-retry dialogs uploadMulti() itself uses, carrying
     * forward whichever overrides were already granted, so a second (or
     * third) distinct gate gets its own chance to be overridden instead of
     * silently discarding a photo set that was otherwise fine. */
    private fun retryUploadMulti(
        tagCode: String, staffName: String, main: ByteArray, angle1: ByteArray, angle2: ByteArray,
        overrideDuplicate: Boolean = false, overrideBlur: Boolean = false, overrideVisibility: Boolean = false
    ) {
        lifecycleScope.launch {
            val result = try {
                UploadClient.saveMulti(
                    serverUrl(), tagCode, staffName, main, angle1, angle2,
                    overrideDuplicate, overrideBlur, overrideVisibility
                )
            } catch (e: Exception) {
                logCaptureEvent("upload_multi_retry_exception", mapOf("message" to e.message))
                null
            }
            if (result == null) {
                showUploadFailedPopup("Upload failed — check server URL/network.")
                return@launch
            }
            when {
                result.ok -> {
                    logCaptureEvent("upload_multi_retry_ok")
                    showItemSavedPopup(tagCode)
                }
                result.duplicate -> confirmOverrideAndRetry("Duplicate tag $tagCode — save anyway?") { overrideDup ->
                    retryUploadMulti(tagCode, staffName, main, angle1, angle2,
                        overrideDuplicate = overrideDup, overrideBlur = overrideBlur, overrideVisibility = overrideVisibility)
                }
                result.blurry -> confirmOverrideAndRetry("A photo in the set looked blurry — save anyway?") { overrideBlur2 ->
                    retryUploadMulti(tagCode, staffName, main, angle1, angle2,
                        overrideDuplicate = overrideDuplicate, overrideBlur = overrideBlur2, overrideVisibility = overrideVisibility)
                }
                result.notVisible -> confirmOverrideAndRetry("Jewellery not clearly visible — save anyway?") { overrideVis ->
                    retryUploadMulti(tagCode, staffName, main, angle1, angle2,
                        overrideDuplicate = overrideDuplicate, overrideBlur = overrideBlur, overrideVisibility = overrideVis)
                }
                else -> {
                    logCaptureEvent("upload_multi_retry_failed", mapOf("error" to result.error))
                    showUploadFailedPopup("Save failed: ${result.error}")
                }
            }
        }
    }

    private fun uploadPair() {
        val jewel = jewelJpeg
        val tag = tagJpeg
        val tagCode = stableTagCode
        if (jewel == null || tag == null || tagCode == null) {
            setStatus("Missing photo — retake", ready = false)
            resetForNewItem(Phase.TAG)
            return
        }
        phase = Phase.UPLOADING
        setStatus("Securing photos locally…", ready = false)
        val serverUrl = serverUrl()
        val staffName = prefs.getString("staff_name", "") ?: ""
        if (serverUrl.isBlank()) {
            logCaptureEvent("upload_blocked_no_server_url")
            Toast.makeText(this, "Set the capture server URL in Settings first", Toast.LENGTH_LONG).show()
            showSettingsDialog()
            resetForNewItem(Phase.TAG)
            return
        }
        logCaptureEvent("upload_pair_stage_attempt")
        lifecycleScope.launch {
            val staged = try {
                CaptureUploadQueue.stagePair(
                    applicationContext, serverUrl, tagCode, staffName, jewel, tag
                )
            } catch (e: Exception) {
                Log.e(TAG, "Pair local staging failed", e)
                logCaptureEvent("upload_pair_stage_failed", mapOf("message" to e.message))
                showUploadFailedPopup("Could not secure photos locally: ${e.message}")
                return@launch
            }
            logCaptureEvent("upload_pair_queued", mapOf("job_id" to staged.id))
            jewelJpeg = null
            tagJpeg = null
            Toast.makeText(this@MainActivity, "Queued $tagCode — uploading in background", Toast.LENGTH_SHORT).show()
            finishOrResetForNewItem()
        }
    }

    /** Same chained-override fix as retryUploadMulti -- see its doc comment. */
    private fun retryUpload(
        tagCode: String, staffName: String, jewel: ByteArray, tag: ByteArray,
        overrideDuplicate: Boolean = false, overrideBlur: Boolean = false, overrideVisibility: Boolean = false
    ) {
        lifecycleScope.launch {
            val result = try {
                UploadClient.savePair(
                    serverUrl(), tagCode, staffName, jewel, tag,
                    overrideDuplicate, overrideBlur, overrideVisibility
                )
            } catch (e: Exception) {
                logCaptureEvent("upload_pair_retry_exception", mapOf("message" to e.message))
                null
            }
            if (result == null) {
                showUploadFailedPopup("Upload failed — check server URL/network.")
                return@launch
            }
            when {
                result.ok -> {
                    logCaptureEvent("upload_pair_retry_ok")
                    Toast.makeText(this@MainActivity, "Saved: $tagCode", Toast.LENGTH_SHORT).show()
                    finishOrResetForNewItem()
                }
                result.duplicate -> confirmOverrideAndRetry("Duplicate tag $tagCode — save anyway?") { overrideDup ->
                    retryUpload(tagCode, staffName, jewel, tag,
                        overrideDuplicate = overrideDup, overrideBlur = overrideBlur, overrideVisibility = overrideVisibility)
                }
                result.blurry -> confirmOverrideAndRetry("Jewel photo looked blurry — save anyway?") { overrideBlur2 ->
                    retryUpload(tagCode, staffName, jewel, tag,
                        overrideDuplicate = overrideDuplicate, overrideBlur = overrideBlur2, overrideVisibility = overrideVisibility)
                }
                result.notVisible -> confirmOverrideAndRetry("Jewellery not clearly visible — save anyway?") { overrideVis ->
                    retryUpload(tagCode, staffName, jewel, tag,
                        overrideDuplicate = overrideDuplicate, overrideBlur = overrideBlur, overrideVisibility = overrideVis)
                }
                else -> {
                    logCaptureEvent("upload_pair_retry_failed", mapOf("error" to result.error))
                    showUploadFailedPopup("Save failed: ${result.error}")
                }
            }
        }
    }

    /** After a successful save: if this session was handed off from the
     * browser (capturecam://start), return control to it immediately --
     * the browser stays the anchor for tray/recommended-item context, this
     * app's only job was the one capture. Otherwise (launched directly
     * from the home screen) keep looping for the next item in-app, since
     * that's faster for a standalone multi-item batch session. */
    private fun finishOrResetForNewItem() {
        if (launchedFromBrowser) {
            handler.postDelayed({ finish() }, 600)
        } else {
            resetForNewItem(Phase.TAG)
        }
    }

    /** Explicit confirmation before the pipeline moves on -- a silent Toast
     * was easy to miss mid-workflow with hands full of jewellery/tags. The
     * operator has to actually acknowledge the save before the next item
     * starts, rather than the app silently looping underneath them. */
    private fun showItemSavedPopup(tagCode: String) {
        AlertDialog.Builder(this)
            .setTitle("Saved")
            .setMessage("3-angle set saved for $tagCode.")
            .setCancelable(false)
            .setPositiveButton("Next item") { _, _ -> finishOrResetForNewItem() }
            .show()
    }

    private fun confirmOverrideAndRetry(message: String, onChoice: (Boolean) -> Unit) {
        AlertDialog.Builder(this)
            .setMessage(message)
            .setPositiveButton("Save anyway") { _, _ -> onChoice(true) }
            .setNegativeButton("Retake") { _, _ -> onChoice(false); resetForNewItem(Phase.TAG) }
            .setCancelable(false)
            .show()
    }

    // ---------------------------------------------------------------- State reset

    private fun resetForNewItem(next: Phase) {
        phase = next
        armed = next == Phase.TAG
        armedAt = System.currentTimeMillis()
        stepFocusAttempts = 0
        resetSonyAutomaticAfBudget()
        maxUsableZoom = Float.MAX_VALUE
        maxUsableZoomStuckSince = 0L
        autoFired = false
        latestMaterial = null
        lastZoomChangeAt = 0L
        focusTriggeredThisLevel = false
        isZooming = false
        stallGraceAt = 0L
        materialLossStreak = 0
        readyStreak = 0
        exposureClipStreak = 0
        exposureClearStreak = 0
        manualExposureOverride = false
        lastTrackingLogAt = 0L
        lastCenterLimitLogAt = 0L
        jewelCaptureRetries = 0
        angleCaptureInFlight = false
        angleCaptureRetryCount = 0
        angleFocusTriggered = false
        clearStandDistanceGuide()
        compositionRoiLocked = false
        centerEmaCx = null
        centerEmaCy = null
        lastNudgeAxis = CenterAxis.NONE
        lastNudgeErrorMagnitude = null
        centerDivergeStreak = 0
        centeringSettledUntil = 0L
        if (manualModeActive) {
            manualModeActive = false
            binding.manualModeText.text = getString(R.string.auto_tracking)
            binding.resumeAutoButton.visibility = View.GONE
        }
        manualFocusLocked = false
        if (next == Phase.JEWEL) {
            // Normal completion already undid these via
            // undoCenteringThenAdvance() before calling here -- this is
            // just the defensive reset for abort/cancel paths that skip it.
            centeringPanMs = 0
            centeringTiltMs = 0
            centeringAttempts = 0
            lastCenterAxis = CenterAxis.NONE
            centerAvoidAxis = CenterAxis.NONE
            lockedBoxCenter = null
            huntPhase = HuntPhase.SCAN_DOWN
            huntPhaseMsSpent = 0
            huntStartedAt = 0L
        }
        if (next == Phase.TAG) {
            // TAG is the fresh-item entry point under the #76 flip (tag
            // scans FIRST) -- this is where a genuinely NEW item starts,
            // so the tag fields get cleared here now, not on JEWEL entry.
            barcodeAttempts = 0
            lastBarcodeCount = -1
            lastBarcodeError = null
            tagJpeg = null
            resetSonyTagBurst()
            tagCodeHistory = mutableListOf()
            stableTagCode = null
            resolvedCategoryKey = null
            categoryResolutionCode = null
            categoryResolutionError = null
            invalidTagCode = null
            studFlagPersisted = null
            studAutoGuess = false
            wrongShapeSince = 0L
            aiShapeAdviceCategory = null
            aiShapeOverrideUntil = 0L
            updateStudStatusUi()
            // Auto-exposure bias is per-item, not permanent -- a piece
            // that needed heavy negative EV shouldn't leave the NEXT
            // item starting under-exposed.
            queueAutoExposure(0f)
            // Defensive path for cancellations, browser handoffs and app
            // re-entry. Normal successful capture already starts this reset
            // inside uploadCapturedSet(), where it overlaps local staging.
            resetSonyZoomFullyWideForNextTag()
            // Sony remains in AF-C/Pre-AF. Do not send a remote-touch nudge:
            // it interrupts Live View on this body.
        }
        if (next == Phase.JEWEL) {
            // This item may zoom in. Its eventual completion must issue a
            // fresh endpoint reset for the following tag.
            wideResetComplete = false
            wideResetAttempts = 0
            // Deliberately does NOT touch tagJpeg/stableTagCode/
            // tagCodeHistory -- entering JEWEL now means "tag already
            // scanned, go shoot the jewel photos for THIS item," not a new
            // item. Clearing them here would silently discard the tag just
            // captured (confirmed as the failure mode this would produce
            // during the #76 flip work, 2026-08-18).
            jewelJpeg = null
            angle1Jpeg = null; angle1Validated = false; angle1NeedsRetake = false
            angle2Jpeg = null
            setCameraZoomRatio(1f)
        }
        applySonyFocusAreaForPhase()
        setStatus(if (next == Phase.JEWEL) "Center the ornament, front side up…" else "Show the tag QR/barcode…", ready = false)
    }

    private fun setStatus(text: String, ready: Boolean) {
        binding.statusText.text = text
        binding.statusText.setBackgroundResource(if (ready) R.drawable.bg_card_ready else R.drawable.bg_card)
        val material = latestMaterial
        binding.debugText.text = if (phase == Phase.JEWEL) {
            val range = cameraZoomRange()
            val base = "zoom=%.1fx range=[%.1f,%.1f]  coverage=%.3f  detail=%s  sonyAF=%s\nev=%.2f  goldClip=%.3f  sceneClip=%.3f".format(
                cameraZoomRatio(),
                range.start, range.endInclusive,
                material?.coverage ?: 0f,
                if (latestSharpness >= SHARPNESS_THRESHOLD) "PASS" else "LOW",
                afStateLabel(cameraAfState()),
                autoExposureEv,
                material?.highlightClipFraction ?: 0f,
                material?.sceneClipFraction ?: 0f
            )
            val symmetryWarning = danglerSymmetryWarning(material)
            if (symmetryWarning != null) "$base\n$symmetryWarning" else base
        } else ""
        updateStepIndicator()
    }

    /** Advisory-only (explicit request, 2026-08-19): staff flagged that a
     * bent-under or hidden ghungroo/dangler is easy to miss by eye through
     * the phone screen while framing a symmetric pair (matched earrings)
     * or a piece with mirror-symmetric halves (WATI's twin bowls). Splits
     * the small "dangler" blobs MaterialDetector already found in the
     * lower portion of the piece (see its danglerBlobs doc comment) by
     * which side of the piece's own horizontal midline they fall on, and
     * flags a left/right COUNT mismatch. Deliberately never gates or
     * blocks capture -- only applies to categories with a genuine
     * mirror-symmetric pair/halves (CategoryOrientation), and only once
     * resolvedCategoryKey has actually come back from the server, so an
     * unresolved or non-symmetric category silently shows nothing rather
     * than a false alarm. */
    private fun danglerSymmetryWarning(material: MaterialDetector.Result?): String? {
        if (!CategoryOrientation.hasMirrorSymmetry(resolvedCategoryKey)) return null
        val bounds = material?.bounds ?: return null
        if (material.danglerBlobs.isEmpty()) return null
        val midX = (bounds.x0 + bounds.x1) / 2f
        var left = 0
        var right = 0
        for (b in material.danglerBlobs) {
            val cx = (b.x0 + b.x1) / 2f
            if (cx < midX) left++ else right++
        }
        if (left == right) return null
        return "⚠ danglers L=$left R=$right — check symmetry"
    }

    /** Drives the TAG/QR -> MAIN VIEW -> LEFT ANGLE -> RIGHT ANGLE step bar
     * from state that already exists (phase, inAngleSequence, angle1Jpeg)
     * -- purely a progress display, doesn't gate or alter any capture
     * logic. Called every setStatus() so it never drifts out of sync with
     * what the pipeline is actually doing. Completed steps go green,
     * the current step goes purple, everything else stays neutral. */
    private fun updateStepIndicator() {
        val currentStep = when {
            phase == Phase.TAG -> 1
            phase == Phase.JEWEL && !inAngleSequence -> 2
            phase == Phase.JEWEL && inAngleSequence && angle1Jpeg == null -> 3
            phase == Phase.JEWEL && inAngleSequence -> 4
            phase == Phase.UPLOADING -> 4
            else -> 1
        }
        val steps = listOf(binding.stepTag, binding.stepMain, binding.stepLeft, binding.stepRight)
        steps.forEachIndexed { i, view ->
            val stepNumber = i + 1
            when {
                stepNumber < currentStep -> {
                    view.setBackgroundResource(R.drawable.bg_step_done)
                    view.setTextColor(0xFFFFFFFF.toInt())
                }
                stepNumber == currentStep -> {
                    view.setBackgroundResource(R.drawable.bg_step_active)
                    view.setTextColor(0xFFFFFFFF.toInt())
                }
                else -> {
                    view.setBackgroundResource(R.drawable.bg_step_inactive)
                    view.setTextColor(resources.getColor(R.color.text_muted, theme))
                }
            }
        }
    }

    private fun afStateLabel(state: Int?): String = when (state) {
        null -> "—"
        CaptureResult.CONTROL_AF_STATE_INACTIVE -> "inactive"
        CaptureResult.CONTROL_AF_STATE_PASSIVE_SCAN -> "scanning"
        CaptureResult.CONTROL_AF_STATE_PASSIVE_FOCUSED -> "passive-focused"
        CaptureResult.CONTROL_AF_STATE_ACTIVE_SCAN -> "active-scan"
        CaptureResult.CONTROL_AF_STATE_FOCUSED_LOCKED -> "LOCKED"
        CaptureResult.CONTROL_AF_STATE_NOT_FOCUSED_LOCKED -> "FAILED"
        CaptureResult.CONTROL_AF_STATE_PASSIVE_UNFOCUSED -> "passive-unfocused"
        else -> "state=$state"
    }

    // ---------------------------------------------------------------- Settings

    private fun bindSonySpinner(spinner: Spinner, labels: Array<String>, selection: Int) {
        spinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, labels)
        spinner.setSelection(selection.coerceIn(0, labels.lastIndex))
    }

    private fun savedSonyQualitySettings(): SonyQualitySettings {
        val profile = prefs.getInt("sony_quality_profile", 0).coerceIn(0, 2)
        val evThirds = (autoExposureEv * 3f).roundToInt()
        val evMilli = ((evThirds * 1_000f / 3f) / 100f).roundToInt() * 100
        if (profile == 0) {
            // Restored to match the production-verified exposure behavior
            // (2026-08-25 checkpoint, confirmed "perfect" on real E2E items):
            // aperture-priority + ISO 100, no fixed shutter override. This
            // candidate branch had switched profile 0 to Manual+AutoISO+1/100
            // to chase live-view fps, but that changes what the operator sees
            // during the pre-capture exposure-adjustment cycle -- explicitly
            // told to preserve that cycle exactly, not the fps rationale.
            // The new streaming-safe property-write path (applyQualitySettings
            // via setControlDeviceAStreamingSafe) still applies these values
            // without the old HTTP-stream release/reopen -- only the VALUES
            // reverted, not the write mechanism.
            return SonyQualitySettings(
                exposureMode = 131_075,
                iso = 100,
                whiteBalance = 2,
                stillFileFormat = 2,
                jpegQuality = 1,
                imageSize = 1,
                stillImageTransferSize = 1,
                rawFileType = 6,
                aspectRatio = 1,
                dynamicRangeOptimizer = 1,
                creativeLook = 1,
                fNumberTimes100 = 800,
                exposureCompensationMilliEv = evMilli,
                focusMode = 0x8004,
                focusArea = 259,
                exposureMeteringMode = 0x8001
            )
        }
        if (profile == 1) {
            return SonyQualitySettings(
                exposureMode = 294_912,
                iso = 0x00FF_FFFF,
                whiteBalance = 2,
                stillFileFormat = 2,
                jpegQuality = 1,
                imageSize = 1,
                stillImageTransferSize = 1,
                rawFileType = 6,
                aspectRatio = 1,
                dynamicRangeOptimizer = 1,
                creativeLook = 1,
                exposureCompensationMilliEv = evMilli,
                focusMode = 0x8004,
                focusArea = 259,
                exposureMeteringMode = 0x8001
            )
        }
        val apertureIndex = prefs.getInt("sony_aperture_index", 0)
            .coerceIn(0, SONY_APERTURE_VALUES.lastIndex)
        val shutterIndex = prefs.getInt("sony_shutter_index", 0)
            .coerceIn(0, SONY_SHUTTER_VALUES.lastIndex)
        val shutter = SONY_SHUTTER_VALUES[shutterIndex]
        val exposureMode = SONY_EXPOSURE_MODE_VALUES[
            prefs.getInt("sony_exposure_mode_index", 0)
                .coerceIn(0, SONY_EXPOSURE_MODE_VALUES.lastIndex)
        ]
        val apertureControlledByMode = exposureMode == 131_075 || exposureMode == 1
        val shutterControlledByMode = exposureMode == 196_612 || exposureMode == 1
        return SonyQualitySettings(
            exposureMode = exposureMode,
            iso = SONY_ISO_VALUES[
                prefs.getInt("sony_iso_index", 0).coerceIn(0, SONY_ISO_VALUES.lastIndex)
            ],
            whiteBalance = SONY_WB_VALUES[
                prefs.getInt("sony_wb_index", 0).coerceIn(0, SONY_WB_VALUES.lastIndex)
            ],
            stillFileFormat = SONY_FILE_FORMAT_VALUES[
                prefs.getInt("sony_file_format_index", 0)
                    .coerceIn(0, SONY_FILE_FORMAT_VALUES.lastIndex)
            ],
            jpegQuality = SONY_JPEG_QUALITY_VALUES[
                prefs.getInt("sony_jpeg_quality_index", 0)
                    .coerceIn(0, SONY_JPEG_QUALITY_VALUES.lastIndex)
            ],
            imageSize = SONY_IMAGE_SIZE_VALUES[
                prefs.getInt("sony_image_size_index", 0)
                    .coerceIn(0, SONY_IMAGE_SIZE_VALUES.lastIndex)
            ],
            stillImageTransferSize = SONY_TRANSFER_SIZE_VALUES[
                prefs.getInt("sony_transfer_size_index", 0)
                    .coerceIn(0, SONY_TRANSFER_SIZE_VALUES.lastIndex)
            ],
            rawFileType = SONY_RAW_TYPE_VALUES[
                prefs.getInt("sony_raw_type_index", 0)
                    .coerceIn(0, SONY_RAW_TYPE_VALUES.lastIndex)
            ],
            aspectRatio = SONY_ASPECT_RATIO_VALUES[
                prefs.getInt("sony_aspect_ratio_index", 0)
                    .coerceIn(0, SONY_ASPECT_RATIO_VALUES.lastIndex)
            ],
            dynamicRangeOptimizer = SONY_DRO_VALUES[
                prefs.getInt("sony_dro_index", 0).coerceIn(0, SONY_DRO_VALUES.lastIndex)
            ],
            creativeLook = SONY_CREATIVE_LOOK_VALUES[
                prefs.getInt("sony_creative_look_index", 0)
                    .coerceIn(0, SONY_CREATIVE_LOOK_VALUES.lastIndex)
            ],
            fNumberTimes100 = if (apertureControlledByMode) {
                SONY_APERTURE_VALUES[apertureIndex]
            } else null,
            shutterNumerator = if (shutterControlledByMode) shutter?.first else null,
            shutterDenominator = if (shutterControlledByMode) shutter?.second else null,
            exposureCompensationMilliEv = evMilli,
            focusMode = SONY_FOCUS_MODE_VALUES[
                prefs.getInt("sony_focus_mode_index", 0)
                    .coerceIn(0, SONY_FOCUS_MODE_VALUES.lastIndex)
            ],
            focusArea = SONY_FOCUS_AREA_VALUES[
                prefs.getInt("sony_focus_area_index", 0)
                    .coerceIn(0, SONY_FOCUS_AREA_VALUES.lastIndex)
            ],
            exposureMeteringMode = SONY_METERING_VALUES[
                prefs.getInt("sony_metering_index", 0)
                    .coerceIn(0, SONY_METERING_VALUES.lastIndex)
            ]
        )
    }

    private fun scheduleSavedSonyQualitySettings() {
        if (sonyQualityApplyScheduled) return
        sonyQualityApplyScheduled = true
        handler.postDelayed({
            sonyQualityApplyScheduled = false
            if (activeCameraSource != ProductionCameraSource.SONY || !sonyProduction.isAvailable) {
                return@postDelayed
            }
            val settings = savedSonyQualitySettings()
            sonyProduction.applyQualitySettings(settings) { ok ->
                Log.i(TAG, "Sony saved quality profile applied ok=$ok settings=$settings")
                if (ok) applySonyFocusAreaForPhase()
            }
        }, 500L)
    }

    /** TAG uses AF-C Wide so a foreground label entering anywhere near the
     * centre is acquired without repeated touch-focus commands. JEWEL
     * restores the operator's configured focus area. One property write per
     * phase preserves the 25fps stream; a 900ms touch-focus loop measured
     * only ~14fps and was removed before production handoff. */
    private fun applySonyFocusAreaForPhase() {
        if (activeCameraSource != ProductionCameraSource.SONY || !sonyProduction.isAvailable) return
        val target = if (phase == Phase.TAG) {
            SONY_TAG_FOCUS_AREA_WIDE
        } else {
            SONY_JEWEL_FOCUS_AREA_TRACKING_SPOT_L
        }
        sonyProduction.setFocusArea(target) { ok ->
            Log.i(TAG, "Sony phase focus area phase=$phase value=$target ok=$ok")
        }
    }

    private fun showSettingsDialog() {
        val previousCameraMode = requestedCameraMode()
        val dialogBinding = DialogSettingsBinding.inflate(layoutInflater)
        dialogBinding.serverUrlInput.setText(serverUrl())
        dialogBinding.staffNameInput.setText(prefs.getString("staff_name", ""))
        bindSonySpinner(
            dialogBinding.cameraModeSpinner,
            CAMERA_MODE_LABELS,
            prefs.getInt(PREF_CAMERA_MODE, 0)
        )
        bindSonySpinner(
            dialogBinding.sonyProfileSpinner,
            SONY_PROFILE_LABELS,
            prefs.getInt("sony_quality_profile", 0)
        )
        bindSonySpinner(
            dialogBinding.sonyIsoSpinner,
            SONY_ISO_LABELS,
            prefs.getInt("sony_iso_index", 0)
        )
        bindSonySpinner(
            dialogBinding.sonyExposureModeSpinner,
            SONY_EXPOSURE_MODE_LABELS,
            prefs.getInt("sony_exposure_mode_index", 0)
        )
        bindSonySpinner(
            dialogBinding.sonyApertureSpinner,
            SONY_APERTURE_LABELS,
            prefs.getInt("sony_aperture_index", 0)
        )
        bindSonySpinner(
            dialogBinding.sonyShutterSpinner,
            SONY_SHUTTER_LABELS,
            prefs.getInt("sony_shutter_index", 0)
        )
        bindSonySpinner(
            dialogBinding.sonyWhiteBalanceSpinner,
            SONY_WB_LABELS,
            prefs.getInt("sony_wb_index", 0)
        )
        bindSonySpinner(
            dialogBinding.sonyFocusModeSpinner,
            SONY_FOCUS_MODE_LABELS,
            prefs.getInt("sony_focus_mode_index", 0)
        )
        bindSonySpinner(
            dialogBinding.sonyFocusAreaSpinner,
            SONY_FOCUS_AREA_LABELS,
            prefs.getInt("sony_focus_area_index", 0)
        )
        bindSonySpinner(
            dialogBinding.sonyMeteringSpinner,
            SONY_METERING_LABELS,
            prefs.getInt("sony_metering_index", 0)
        )
        bindSonySpinner(dialogBinding.sonyFileFormatSpinner, SONY_FILE_FORMAT_LABELS, prefs.getInt("sony_file_format_index", 0))
        bindSonySpinner(dialogBinding.sonyRawTypeSpinner, SONY_RAW_TYPE_LABELS, prefs.getInt("sony_raw_type_index", 0))
        bindSonySpinner(dialogBinding.sonyJpegQualitySpinner, SONY_JPEG_QUALITY_LABELS, prefs.getInt("sony_jpeg_quality_index", 0))
        bindSonySpinner(dialogBinding.sonyImageSizeSpinner, SONY_IMAGE_SIZE_LABELS, prefs.getInt("sony_image_size_index", 0))
        bindSonySpinner(dialogBinding.sonyTransferSizeSpinner, SONY_TRANSFER_SIZE_LABELS, prefs.getInt("sony_transfer_size_index", 0))
        bindSonySpinner(dialogBinding.sonyAspectRatioSpinner, SONY_ASPECT_RATIO_LABELS, prefs.getInt("sony_aspect_ratio_index", 0))
        bindSonySpinner(dialogBinding.sonyDroSpinner, SONY_DRO_LABELS, prefs.getInt("sony_dro_index", 0))
        bindSonySpinner(dialogBinding.sonyCreativeLookSpinner, SONY_CREATIVE_LOOK_LABELS, prefs.getInt("sony_creative_look_index", 0))
        AlertDialog.Builder(this)
            .setTitle(R.string.settings)
            .setView(dialogBinding.root)
            .setPositiveButton(R.string.save) { _, _ ->
                prefs.edit()
                    .putString("server_url", dialogBinding.serverUrlInput.text.toString().trim())
                    .putString("staff_name", dialogBinding.staffNameInput.text.toString().trim())
                    .putInt(PREF_CAMERA_MODE, dialogBinding.cameraModeSpinner.selectedItemPosition)
                    .putInt("sony_quality_profile", dialogBinding.sonyProfileSpinner.selectedItemPosition)
                    .putInt("sony_iso_index", dialogBinding.sonyIsoSpinner.selectedItemPosition)
                    .putInt(
                        "sony_exposure_mode_index",
                        dialogBinding.sonyExposureModeSpinner.selectedItemPosition
                    )
                    .putInt("sony_aperture_index", dialogBinding.sonyApertureSpinner.selectedItemPosition)
                    .putInt("sony_shutter_index", dialogBinding.sonyShutterSpinner.selectedItemPosition)
                    .putInt("sony_wb_index", dialogBinding.sonyWhiteBalanceSpinner.selectedItemPosition)
                    .putInt("sony_focus_mode_index", dialogBinding.sonyFocusModeSpinner.selectedItemPosition)
                    .putInt("sony_focus_area_index", dialogBinding.sonyFocusAreaSpinner.selectedItemPosition)
                    .putInt("sony_metering_index", dialogBinding.sonyMeteringSpinner.selectedItemPosition)
                    .putInt("sony_file_format_index", dialogBinding.sonyFileFormatSpinner.selectedItemPosition)
                    .putInt("sony_raw_type_index", dialogBinding.sonyRawTypeSpinner.selectedItemPosition)
                    .putInt("sony_jpeg_quality_index", dialogBinding.sonyJpegQualitySpinner.selectedItemPosition)
                    .putInt("sony_image_size_index", dialogBinding.sonyImageSizeSpinner.selectedItemPosition)
                    .putInt("sony_transfer_size_index", dialogBinding.sonyTransferSizeSpinner.selectedItemPosition)
                    .putInt("sony_aspect_ratio_index", dialogBinding.sonyAspectRatioSpinner.selectedItemPosition)
                    .putInt("sony_dro_index", dialogBinding.sonyDroSpinner.selectedItemPosition)
                    .putInt("sony_creative_look_index", dialogBinding.sonyCreativeLookSpinner.selectedItemPosition)
                    .apply()
                // A deliberate switch is the only path allowed to change
                // camera families. Reset the permission prompt gate so an
                // operator choosing Smartphone can grant it immediately.
                val newCameraMode = requestedCameraMode()
                if (newCameraMode != previousCameraMode) {
                    cameraModeEpoch += 1L
                    inAngleSequence = false
                    hideReadyButton()
                    rsc2.stopAndReturnToCenter()
                    jewelJpeg = null
                    angle1Jpeg = null; angle1Validated = false; angle1NeedsRetake = false
                    angle2Jpeg = null
                    resetForNewItem(Phase.TAG)
                    Toast.makeText(
                        this,
                        "Camera mode changed; current item reset",
                        Toast.LENGTH_SHORT
                    ).show()
                }
                cameraPermissionRequestedThisSession = false
                applyRequestedCameraMode(allowPermissionPrompt = true)
                if (requestedCameraMode() == RequestedCameraMode.DSLR && sonyProduction.isAvailable) {
                    val settings = savedSonyQualitySettings()
                    sonyProduction.applyQualitySettings(settings) { ok ->
                        Toast.makeText(
                            this,
                            if (ok) "Sony quality settings applied" else "Sony quality settings failed",
                            Toast.LENGTH_SHORT
                        ).show()
                    }
                }
            }
            .setNegativeButton(R.string.cancel, null)
            .setNeutralButton("RSC2 BLE test") { _, _ ->
                // Sony and RSC2 each accept one production owner. Release
                // MainActivity before diagnostics opens; onResume restores
                // both when the operator returns.
                mainScreenActive = false
                if (::sonyProduction.isInitialized) sonyProduction.stop()
                rsc2.disconnect()
                startActivity(Intent(this, BleDiagnosticsActivity::class.java))
            }
            .show()
    }

    /** Lists every background upload parked in needs_review and lets staff
     * act on each one (2026-08-26 fix -- see CaptureUploadQueue). Nothing
     * here is automatic: retry, override, and discard are all explicit
     * per-item staff decisions. */
    private fun showUploadReviewDialog() {
        val items = CaptureUploadQueue.listNeedsReview(this)
        if (items.isEmpty()) {
            Toast.makeText(this, "No uploads need review", Toast.LENGTH_SHORT).show()
            return
        }
        val labels = items.map { "${it.tagCode}  (${it.error ?: "unknown"})" }.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("Needs review (${items.size})")
            .setItems(labels) { _, index -> showUploadReviewActionDialog(items[index]) }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun showUploadReviewActionDialog(item: CaptureUploadQueue.ReviewItem) {
        val actions = mutableListOf("Retry as-is", "Discard (delete originals)")
        // Only offer the specific override that matches what the server
        // actually rejected -- overriding a duplicate should not also
        // silently force past a real blur rejection the server never made.
        when (item.error) {
            "duplicate" -> actions.add(1, "Save anyway (duplicate)")
            "blurry" -> actions.add(1, "Save anyway (blurry)")
            "not_clearly_visible" -> actions.add(1, "Save anyway (not clearly visible)")
        }
        AlertDialog.Builder(this)
            .setTitle(item.tagCode)
            .setMessage("Rejected: ${item.error ?: "unknown error"}")
            .setItems(actions.toTypedArray()) { _, index ->
                when (actions[index]) {
                    "Retry as-is" -> {
                        CaptureUploadQueue.retryWithOverride(this, item.dir)
                        Toast.makeText(this, "Retrying ${item.tagCode}", Toast.LENGTH_SHORT).show()
                    }
                    "Discard (delete originals)" -> {
                        CaptureUploadQueue.discard(item.dir)
                        Toast.makeText(this, "Discarded ${item.tagCode}", Toast.LENGTH_SHORT).show()
                    }
                    "Save anyway (duplicate)" -> {
                        CaptureUploadQueue.retryWithOverride(this, item.dir, overrideDuplicate = true)
                        Toast.makeText(this, "Saving ${item.tagCode} anyway", Toast.LENGTH_SHORT).show()
                    }
                    "Save anyway (blurry)" -> {
                        CaptureUploadQueue.retryWithOverride(this, item.dir, overrideBlur = true)
                        Toast.makeText(this, "Saving ${item.tagCode} anyway", Toast.LENGTH_SHORT).show()
                    }
                    "Save anyway (not clearly visible)" -> {
                        CaptureUploadQueue.retryWithOverride(this, item.dir, overrideVisibility = true)
                        Toast.makeText(this, "Saving ${item.tagCode} anyway", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    override fun onDestroy() {
        super.onDestroy()
        // Clears tickRunnable and any pending scheduleGimbalRetry callback
        // both -- the latter is posted as an anonymous lambda (no stable
        // Runnable reference to remove individually), and nothing should
        // fire against this Activity once it's destroyed anyway.
        handler.removeCallbacksAndMessages(null)
        barcodeScanner.close()
        barcodeExecutor.shutdownNow()
        jewelAnalysisExecutor.shutdownNow()
        if (::sonyProduction.isInitialized) sonyProduction.stop()
        rsc2.disconnect()
        try { unregisterReceiver(testMoveReceiver) } catch (_: IllegalArgumentException) {}
        try { unregisterReceiver(testExposureReceiver) } catch (_: IllegalArgumentException) {}
        try { unregisterReceiver(testZoomReceiver) } catch (_: IllegalArgumentException) {}
        try { unregisterReceiver(testZoomMotorReceiver) } catch (_: IllegalArgumentException) {}
        try { unregisterReceiver(testFocusReceiver) } catch (_: IllegalArgumentException) {}
        try { unregisterReceiver(testSonyCaptureReceiver) } catch (_: IllegalArgumentException) {}
        try { unregisterReceiver(testSonyCardObjectsReceiver) } catch (_: IllegalArgumentException) {}
    }
}
