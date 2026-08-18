package com.aradhana.capturecam

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.graphics.RectF
import android.hardware.camera2.CaptureResult
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import android.widget.EditText
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
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.aradhana.capturecam.databinding.ActivityMainBinding
import com.aradhana.capturecam.databinding.DialogSettingsBinding
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.objects.ObjectDetection
import com.google.mlkit.vision.objects.defaults.ObjectDetectorOptions
import kotlinx.coroutines.launch
import org.opencv.core.Mat
import java.nio.ByteBuffer
import kotlin.math.abs
import kotlin.math.min

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
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var cameraProvider: ProcessCameraProvider
    private val focusZoom = FocusZoomController()
    private var imageCapture: ImageCapture? = null
    private var camera: Camera? = null
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
    // Rotation in effect for the most recent MaterialDetector result --
    // needed by bestObjectBox() to convert its points into the same
    // upright-normalized space ML Kit's boxes are already in (uprightPoint
    // convention). Separate from cachedRotationDegrees since that field
    // only updates while the new DINO+MIL pipeline is active.
    private var lastMaterialRotationDegrees = 0
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
    // Explicit, on-demand recenter -- undoes the persisted net pan/tilt
    // drift (loadCenterDrift()'s reference) and physically returns the
    // gimbal to the last confirmed center, regardless of which pipeline
    // (legacy hunt/centering or VisionServoController) produced the drift.
    // adb shell am broadcast -a com.aradhana.capturecam.RECENTER
    private val recenterReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            Log.i(TAG, "recenterReceiver: pan=$centeringPanMs tilt=$centeringTiltMs")
            undoCenteringThenAdvance {
                Log.i(TAG, "recenterReceiver: done")
            }
        }
    }
    // Zeroes the drift counters WITHOUT any physical movement -- treats
    // wherever the gimbal currently, physically is as the new center
    // reference. Use this instead of RECENTER when the stored drift value
    // is known-stale/untrustworthy (e.g. accumulated from since-abandoned
    // testing) and an automatic undo would swing the gimbal by a large,
    // wrong amount with no one watching to confirm it's safe.
    // adb shell am broadcast -a com.aradhana.capturecam.ZERO_DRIFT
    private val zeroDriftReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            Log.i(TAG, "zeroDriftReceiver: was pan=$centeringPanMs tilt=$centeringTiltMs -- zeroing without moving")
            centeringPanMs = 0
            centeringTiltMs = 0
            persistCenterDriftIfChanged()
        }
    }
    // One-way manual nudge -- unlike testMoveReceiver, does NOT auto-return
    // home (that's for a temporary axis test; this is a real, lasting
    // reposition, e.g. "move it a little down" before a search). Updates
    // centeringTiltMs/PanMs so the persisted center-drift reference and
    // RECENTER/job-done-return-to-center all correctly account for it.
    // adb shell am broadcast -a com.aradhana.capturecam.NUDGE --es dir down --el durationMs 250
    // dir: up|down|left|right
    private val nudgeReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val dir = intent.getStringExtra("dir") ?: return
            val durMs = intent.getLongExtra("durationMs", 250L)
            Log.i(TAG, "nudgeReceiver: dir=$dir durationMs=$durMs")
            when (dir) {
                "down" -> {
                    centeringTiltMs -= durMs.toInt()
                    rsc2.moveOut(axis1 = DumlProtocol.AXIS_CENTER - CENTERING_DEFLECTION, durationMs = durMs) {}
                }
                "up" -> {
                    centeringTiltMs += durMs.toInt()
                    rsc2.moveOut(axis1 = DumlProtocol.AXIS_CENTER + CENTERING_DEFLECTION, durationMs = durMs) {}
                }
                "left" -> {
                    centeringPanMs -= durMs.toInt()
                    rsc2.moveOut(axis3 = DumlProtocol.AXIS_CENTER - CENTERING_DEFLECTION, durationMs = durMs) {}
                }
                "right" -> {
                    centeringPanMs += durMs.toInt()
                    rsc2.moveOut(axis3 = DumlProtocol.AXIS_CENTER + CENTERING_DEFLECTION, durationMs = durMs) {}
                }
            }
        }
    }
    private var angle1Jpeg: ByteArray? = null
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
    // Persisted (SharedPreferences, survives app kill/relaunch -- this is
    // the "remember center permanently" reference) net drift from the
    // operator's last confirmed physical center. Updated by BOTH the legacy
    // hunt/centering code (below) AND VisionServoController's servo bursts
    // (applyServoCommand) -- previously only the legacy path updated these,
    // so the new tracking pipeline's motion was invisible to any recenter
    // attempt. Flushed to prefs periodically from tickRunnable rather than
    // at every single mutation site (there are many); losing at most one
    // tick's worth (~150ms) of drift on an app kill is an acceptable trade
    // for not having to touch every call site.
    private var centeringPanMs = 0
    private var centeringTiltMs = 0
    private var lastPersistedPanMs = 0
    private var lastPersistedTiltMs = 0
    private var centeringAttempts = 0

    // Last-known upright-normalized center of the locked gold object, used
    // by bestGoldObjectBox() to reject a same-tick jump onto an unrelated
    // gold cluster elsewhere in frame (see MAX_TARGET_JUMP). Reset whenever
    // tracking restarts for a new item/angle so a fresh search isn't
    // artificially constrained to the previous item's position.
    private var lockedBoxCenter: android.graphics.PointF? = null

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
    private enum class HuntPhase { SCAN_DOWN, SCAN_LEFT, RETURN_PAN, SCAN_RIGHT, GIVE_UP }
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
    private val handler = Handler(Looper.getMainLooper())
    private val barcodeScanner by lazy { BarcodeScanning.getClient() }
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
    private var phase = Phase.JEWEL
    private var armed = false
    private var armedAt = 0L
    private var stepFocusAttempts = 0
    private var maxUsableZoom = Float.MAX_VALUE
    // Timestamp of the last actual zoom change (climb step or backoff
    // step) -- ZOOM_SETTLE_MS after this is the earliest focus may be
    // triggered/judged; ZOOM_STEP_INTERVAL_MS after this is the earliest
    // another climb step may be taken. See tickJewel.
    private var lastZoomChangeAt = 0L
    // Whether a decisive AF trigger has already been sent for the CURRENT
    // zoom level -- the single-shot discipline that stops AF being
    // re-triggered every tick while waiting for its result.
    private var focusTriggeredThisLevel = false
    // True while a smoothZoomTo() ramp is actively running -- tickJewel
    // must not judge focus, take another step, or capture while the zoom
    // is still physically moving. Set false when the ramp reaches target.
    private var isZooming = false
    // Set the instant MAX_STALL_MS first expires, so the safety valve below
    // gets one last forced re-focus attempt instead of shuttering on
    // whatever frame happens to be live at that exact millisecond.
    private var stallGraceAt = 0L
    // One-shot per item: whether the "too close to focus" warning has
    // already extended the stall clock once. Prevents it from looping
    // forever if the piece genuinely never gets moved back.
    private var tooCloseWarned = false
    private var readyStreak = 0
    private var angleStableStreak = 0
    // Bounds how many zoom-in steps centerThenCapture() will take chasing
    // CAPTURE_MIN_OCCUPANCY for ONE angle shot -- reset per side (see
    // promptForSideProfile), not per item.
    private var angleZoomRounds = 0
    private var jewelCaptureRetries = 0
    private var jewelJpeg: ByteArray? = null
    private var tagJpeg: ByteArray? = null
    private var tagCodeHistory = mutableListOf<String>()
    private var stableTagCode: String? = null
    private var autoFired = false
    private var lastAnalysisAt = 0L
    // True while the post-capture preview (image + Retake/Cancel) is on
    // screen -- tickJewel/tickTag must not act on new frames underneath it,
    // or the pipeline could re-fire another auto-capture while the operator
    // is still looking at the last one.
    private var previewShowing = false
    private var previewCountdownRunnable: Runnable? = null

    @Volatile private var latestMaterial: MaterialDetector.Result? = null
    @Volatile private var latestSharpness: Float = 0f
    @Volatile private var barcodeBusy = false
    @Volatile private var barcodeAttempts = 0
    @Volatile private var lastBarcodeCount = -1
    @Volatile private var lastBarcodeError: String? = null

    companion object {
        private const val TAG = "CaptureCam"
        // Guide-box area caps coverage at roughly 0.435 (the blob's box can
        // never exceed the 64%x68% guide region it's measured within) --
        // 0.10 was reachable almost immediately at 1x for any reasonably
        // close item, so the climb rarely ran at all ("doesn't zoom, clicks
        // from far away"). 0.24 asks for the piece to fill about half the
        // guide box before settling, which actually uses the climb.
        private const val MIN_LIVE_COVERAGE = 0.24f
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
        // Was 0.75 -- explicit revised spec (2026-08-18): fill frame > 60%.
        private const val CAPTURE_MIN_OCCUPANCY = 0.60f
        private const val MAX_FOCUS_RETRIES = 2
        private const val ZOOM_BACKOFF_RATIO = 0.8f
        // Gentler per-step ratio (was 1.15x) and a real pause between steps
        // (ZOOM_STEP_INTERVAL_MS) so the climb reads as a smooth, deliberate
        // approach rather than a jumpy series of jerks.
        private const val ZOOM_STEP_RATIO = 1.10f
        private const val ZOOM_STEP_INTERVAL_MS = 350L
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
        private const val TICK_INTERVAL_MS = 150L
        private const val SHARPNESS_THRESHOLD = 40f
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
        // Conservative live-zoom cap per the "physical distance should do
        // most of the framing" principle -- pushing digital/hybrid zoom
        // much past this loses detail the catalogue pipeline later wants.
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
        // Was 4 -- tuned only for MAIN's original "fine pre-capture nudge"
        // case, where the piece was already expected to be roughly
        // centered by the time this runs. Too low for the newer recovery
        // path (see the result.material==false branch in tickJewel) that
        // also uses this same counter to walk an item back from a genuinely
        // extreme starting position (e.g. pinned at the frame edge) --
        // confirmed live: exhausted after 3-4 nudges with the item still
        // nowhere near center, then fell back to doing nothing. Individual
        // nudges are already small and self-correcting (revert-on-overshoot
        // logic above), so the real stopping condition should be "centered"
        // or "genuinely lost", not an arbitrary low attempt count -- raised
        // to a generous budget matching "keep repeating until the occupancy
        // target is met."
        private const val CENTERING_MAX_ATTEMPTS = 20
        // Angle shots reuse the same centering primitive but need a bigger
        // budget: staff places the piece by hand after rotating it, which
        // can start much further off-center than MAIN's fine pre-capture
        // correction ever has to travel from.
        private const val ANGLE_CENTERING_MAX_ATTEMPTS = 8
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
        // (before a separate fix) let zoom climb anyway with no further
        // gimbal correction. Still a placeholder, still well under the
        // ~326° full range, just less prematurely restrictive.
        private const val TILT_MS_LIMIT = 5000
        // Pan has no mechanical hard-stop the way tilt does (full 360°
        // rotation), but still needs a budget cap -- see the doc comment at
        // its call site in attemptCenteringCorrection() for why (target-jump
        // runaway, 2026-08-18). Same order of magnitude as TILT_MS_LIMIT.
        private const val PAN_MS_LIMIT = 5000
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
        // Master switch for the whole pipeline. PARKED (false) for now --
        // 2026-08-18 decision: production launches on the simpler,
        // already-built staff-confirmed flow instead (QR scan -> staff
        // places MAIN, confirms ready -> auto center/zoom/focus/capture ->
        // same for left/right angles -- see tickJewel()'s legacy body and
        // centerThenCapture(), both already implement this). The
        // autonomous DINO+MIL gimbal-hunt pipeline stays in the codebase
        // for a later revisit, not deleted -- just not on the critical
        // path for today's production launch. Flip back to true to resume
        // that work; nothing else needs to change to do so.
        private const val TRACKING_PIPELINE_ACTIVE = false
        private const val DETECTOR_SEND_INTERVAL_MS = 120L
        private const val DETECTOR_FRAME_LONG_EDGE = 960
        private const val DETECTOR_JPEG_QUALITY = 75
        // Tuned up after live testing: the original values (90-260ms bursts,
        // 130ms interval, deflection 220) converged too slowly and read as
        // erratic/stuck on real hardware -- errors were shrinking but not
        // fast enough to keep up with a moving target before the next DINO
        // correction, compounding into visible drift.
        private const val SERVO_INTERVAL_MS = 90L
        private const val SERVO_MIN_MS = 120L
        private const val SERVO_MAX_MS = 380L
        private const val SERVO_MAX_DEFLECTION = 320
        private const val ZOOM_SERVO_INTERVAL_MS = 200L
    }

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) startCamera() else {
            Toast.makeText(this, "Camera permission is required", Toast.LENGTH_LONG).show()
            finish()
        }
    }

    // Best-effort, silent RSC 2 connect -- fails open (single-image mode)
    // if permissions are denied or no gimbal is found; never blocks the
    // camera pipeline on this.
    private val requestBlePermissions = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        if (results.values.all { it }) attemptGimbalConnect()
    }

    private fun attemptGimbalConnect() {
        if (rsc2.isReady) return
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
            requestBlePermissions.launch(missing.toTypedArray())
            return
        }
        rsc2.connect(this) { success ->
            Log.i(TAG, if (success) "RSC 2 connected -- 3-angle capture enabled" else "No RSC 2 found -- single-image mode")
        }
    }

    // True when launched via the capturecam://start deep link from
    // capture.html, rather than tapped from the launcher directly. Drives
    // whether a successful upload hands control back to the browser
    // (finish()) or loops internally for the next item -- see uploadPair.
    private var launchedFromBrowser = false

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
        binding.manualShutterButton.setOnClickListener { forceCaptureCurrentPhase() }
        binding.readyButton.setOnClickListener {
            val action = pendingReadyAction ?: return@setOnClickListener
            hideReadyButton()
            action()
        }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED
        ) {
            startCamera()
        } else {
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
        loadCenterDrift()
        attemptGimbalConnect()
        connectDetector()
        // EXPORTED (not NOT_EXPORTED) deliberately -- this needs to be
        // reachable from `adb shell am broadcast`, which runs as a
        // different UID than this app. Debug-only test hook on a LAN-only
        // tool, not a production attack surface.
        val filter = IntentFilter("com.aradhana.capturecam.TEST_MOVE")
        val recenterFilter = IntentFilter("com.aradhana.capturecam.RECENTER")
        val nudgeFilter = IntentFilter("com.aradhana.capturecam.NUDGE")
        val zeroDriftFilter = IntentFilter("com.aradhana.capturecam.ZERO_DRIFT")
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(testMoveReceiver, filter, RECEIVER_EXPORTED)
            registerReceiver(recenterReceiver, recenterFilter, RECEIVER_EXPORTED)
            registerReceiver(nudgeReceiver, nudgeFilter, RECEIVER_EXPORTED)
            registerReceiver(zeroDriftReceiver, zeroDriftFilter, RECEIVER_EXPORTED)
        } else {
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(testMoveReceiver, filter)
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(recenterReceiver, recenterFilter)
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(nudgeReceiver, nudgeFilter)
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(zeroDriftReceiver, zeroDriftFilter)
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
        if (::cameraProvider.isInitialized) {
            // undoCenteringThenAdvance FIRST, then reset -- resetForNewItem's
            // own centeringPanMs/TiltMs=0 is a silent, non-physical zero
            // (correct only when something upstream already undid the real
            // drift, e.g. the normal angle2-completion path). Called here
            // with no preceding undo, it was discarding real accumulated
            // drift without ever moving the gimbal back -- the app's
            // internal "center" record silently went out of sync with the
            // physical position every time this fired.
            undoCenteringThenAdvance {
                resetForNewItem(Phase.JEWEL)
            }
        }
        attemptGimbalConnect()
    }

    override fun onResume() {
        super.onResume()
        // Coming back to this screen (e.g. from the BLE diagnostics screen,
        // or after turning the gimbal on) is exactly when a previously
        // failed/never-attempted connect should be retried -- onCreate's
        // one-shot attempt otherwise never runs again for the rest of this
        // Activity's life. attemptGimbalConnect() already no-ops if already
        // connected, so this is safe to call on every resume.
        attemptGimbalConnect()
        // Navigating away (e.g. to the BLE diagnostics screen) pauses/stops
        // this Activity, and CameraX's own lifecycle binding didn't reliably
        // bring the camera back on its own -- a capture mid-flight during
        // that window threw "ImageCaptureException: Camera is closed" and
        // left focus/sharpness tracking permanently stuck afterward (the
        // Camera2Interop AF-state callback was attached to the now-dead
        // session). Explicitly rebinding on every resume is the same
        // "re-verify all resources on resume" fix as the gimbal reconnect
        // above -- bindUseCases() itself does cameraProvider.unbindAll()
        // first, so this is safe to call repeatedly.
        if (::cameraProvider.isInitialized) {
            startCamera()
        }
    }

    // ---------------------------------------------------------------- Camera setup

    private fun startCamera() {
        val providerFuture = ProcessCameraProvider.getInstance(this)
        providerFuture.addListener({
            cameraProvider = providerFuture.get()
            bindUseCases()
            logCameraDiagnostics()
            logExtensionsDiagnostics()
        }, ContextCompat.getMainExecutor(this))
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
                val physIds = if (isLogical) ch.physicalCameraIds else emptySet()
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

    private fun bindUseCases() {
        val previewBuilder = Preview.Builder()
        focusZoom.attachCaptureCallback(previewBuilder)
        val preview = previewBuilder.build().also {
            it.setSurfaceProvider(binding.previewView.surfaceProvider)
        }

        val analysis = ImageAnalysis.Builder()
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .build()
        analysis.setAnalyzer(ContextCompat.getMainExecutor(this)) { imageProxy ->
            onFrame(imageProxy)
        }

        imageCapture = ImageCapture.Builder()
            .setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY)
            .build()

        cameraProvider.unbindAll()
        camera = cameraProvider.bindToLifecycle(
            this, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis, imageCapture
        )
        camera?.let { focusZoom.bind(it, getSystemService(android.hardware.camera2.CameraManager::class.java)) }

        resetForNewItem(Phase.JEWEL)
        handler.post(tickRunnable)
    }

    // ---------------------------------------------------------------- Frame analysis

    @OptIn(ExperimentalGetImage::class)
    private fun onFrame(imageProxy: ImageProxy) {
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
                // Once ML Kit has found at least one real object, only trust
                // MaterialDetector's color/contrast points that actually
                // fall inside a genuine detected-object box -- kills stray
                // dots on background/skin/props that happen to pass the
                // color heuristic but were never a real object boundary.
                // Fails open (shows all heuristic points) until ML Kit's
                // first detection lands, so the overlay isn't blank on the
                // very first frames.
                val filteredPoints = if (boxes.isEmpty()) {
                    result.points
                } else {
                    result.points.filter { p ->
                        val up = uprightPoint(p, rotation)
                        boxes.any { it.contains(up[0], up[1]) }
                    }
                }
                // Focus-peaking style overlay -- screen only, see
                // BoundsOverlayView's own doc comment for why this can
                // never leak into the actual captured photo.
                binding.boundsOverlay.update(filteredPoints, imageProxy.width, imageProxy.height, rotation)

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
        val serverUrl = prefs.getString("server_url", "") ?: return
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
        focusZoom.updateTrackingRegion(cmd.targetCx, cmd.targetCy)

        val nowMs = System.currentTimeMillis()
        if (nowMs - lastServoAt >= SERVO_INTERVAL_MS && (cmd.pan != 0f || cmd.tilt != 0f)) {
            lastServoAt = nowMs
            // Attack whichever error is BIGGER, not a blind alternation --
            // blind toggling wastes every other burst re-correcting an
            // axis that's already close while the axis with real error
            // sits idle, which reads as slow/erratic convergence. Only
            // fall back to strict alternation when both errors are
            // comparable, so neither axis gets starved.
            val choosePan = if (cmd.pan != 0f && cmd.tilt != 0f) {
                val panMag = abs(cmd.pan)
                val tiltMag = abs(cmd.tilt)
                if (abs(panMag - tiltMag) > 0.08f) {
                    panMag > tiltMag
                } else {
                    lastServoAxisWasPan = !lastServoAxisWasPan
                    lastServoAxisWasPan
                }
            } else cmd.pan != 0f
            if (choosePan) {
                val mag = abs(cmd.pan)
                val durMs = (SERVO_MIN_MS + mag * (SERVO_MAX_MS - SERVO_MIN_MS)).toLong()
                val deflection = (mag * SERVO_MAX_DEFLECTION).toInt()
                val axis = DumlProtocol.AXIS_CENTER + (if (cmd.pan > 0) deflection else -deflection)
                // Same sign convention as the legacy centering code's
                // centeringPanMs (axis3 above center/pan-right = positive) --
                // shared drift tracker, see loadCenterDrift()'s doc comment.
                centeringPanMs += (if (cmd.pan > 0) durMs else -durMs).toInt()
                rsc2.moveOut(axis3 = axis, durationMs = durMs, settleMs = 0L) {}
            } else {
                val mag = abs(cmd.tilt)
                val durMs = (SERVO_MIN_MS + mag * (SERVO_MAX_MS - SERVO_MIN_MS)).toLong()
                val deflection = (mag * SERVO_MAX_DEFLECTION).toInt()
                // Positive tilt error (ey<0 handled inside VisionServoController)
                // maps the same direction sense as the existing centering code.
                val axis = DumlProtocol.AXIS_CENTER + (if (cmd.tilt > 0) deflection else -deflection)
                centeringTiltMs += (if (cmd.tilt > 0) durMs else -durMs).toInt()
                rsc2.moveOut(axis1 = axis, durationMs = durMs, settleMs = 0L) {}
            }
        }

        if (nowMs - lastZoomServoAt >= ZOOM_SERVO_INTERVAL_MS && cmd.zoomStep != 0f) {
            lastZoomServoAt = nowMs
            val zoom = focusZoom.currentZoomRatio()
            val range = focusZoom.zoomRatioRange()
            val next = (zoom * (1f + cmd.zoomStep)).coerceIn(range.start, min(range.endInclusive, MAX_LIVE_ZOOM_RATIO))
            focusZoom.setZoomRatio(next)
        }
    }

    private fun recordTagCode(code: String?) {
        if (code == null) {
            stableTagCode = null
            return
        }
        val trimmed = code.trim()
        tagCodeHistory = (if (tagCodeHistory.lastOrNull() == trimmed) tagCodeHistory + trimmed else mutableListOf(trimmed))
            .takeLast(3).toMutableList()
        stableTagCode = if (tagCodeHistory.size >= 2) trimmed else null
    }

    // ---------------------------------------------------------------- Pipeline tick

    private val tickRunnable = object : Runnable {
        override fun run() {
            updateGimbalStatusBadge()
            persistCenterDriftIfChanged()
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
            !rsc2.isReady -> "Gimbal: not connected" to 0xB0663333.toInt()
            rsc2.isMoving -> "Gimbal: moving" to 0xB0665C33.toInt()
            else -> "Gimbal: connected" to 0xB0336633.toInt()
        }
        binding.gimbalStatusText.text = text
        binding.gimbalStatusText.setBackgroundColor(color)
    }

    private fun tickTag() {
        if (previewShowing) return
        binding.tagCodeText.text = stableTagCode?.let { "Tag: $it · ready" } ?: "Show the tag QR/barcode…"
        setStatus(stableTagCode?.let { "Tag locked. Capturing…" } ?: "Scanning tag…", ready = stableTagCode != null)
        binding.debugText.text = "attempts=$barcodeAttempts  lastSeen=$lastBarcodeCount" +
            (lastBarcodeError?.let { "  error=$it" } ?: "")
        if (stableTagCode != null && !autoFired) {
            autoFired = true
            captureFullRes { bytes ->
                if (bytes == null) {
                    autoFired = false
                    setStatus("Tag capture failed — retrying", ready = false)
                    return@captureFullRes
                }
                tagJpeg = bytes
                showCapturePreview(
                    bytes,
                    onProceed = { uploadCapturedSet() },
                    onRetake = { retakeTag() },
                    onCancel = { cancelItem() }
                )
            }
        }
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
        if (previewShowing || isZooming || inAngleSequence) return
        val now = System.currentTimeMillis()
        val result = latestMaterial

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
                if (!detectedNow() && rsc2.isReady && now >= huntCooldownUntil) {
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
                if (rsc2.isReady && now >= huntCooldownUntil) {
                    if (huntStartedAt == 0L) huntStartedAt = now
                    if (now - huntStartedAt > HUNT_GRACE_MS) {
                        huntStep()
                        return
                    }
                }
                setStatus("Center the ornament, front side up…", ready = false)
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
            focusZoom.startContinuousTracking()
        }

        updateTrackingRegionFor(result)

        // Simplified core loop (rewritten 2026-08-18, per explicit request
        // to cut this down to the actual rule): CENTER -> ZOOM -> FOCUS ->
        // repeat until the frame is filled with the gold ornament, then
        // capture. bestObjectBox() is the single, gold-exclusive source of
        // truth for "where is it and how big is it" -- no separate
        // MaterialDetector-coverage fallback path, no dual metrics to
        // reconcile.
        //
        // Two things below are NOT arbitrary complexity, they're real
        // hardware constraints that would misbehave if skipped:
        //   - one zoom step per ZOOM_STEP_INTERVAL_MS, then a
        //     ZOOM_SETTLE_MS pause before trusting focus -- judging focus
        //     against a still-moving lens reads as hunting.
        //   - one AF trigger per zoom level, not re-fired every tick while
        //     waiting for Camera2's own result.
        val mlBox = bestObjectBox()
        if (mlBox == null) {
            setStatus("Place the ornament in view…", ready = false)
            return
        }

        val dx = (mlBox.left + mlBox.right) / 2f - 0.5f
        val dy = (mlBox.top + mlBox.bottom) / 2f - 0.5f
        val centered = abs(dx) <= CENTERING_DEADBAND && abs(dy) <= CENTERING_DEADBAND
        val occupancy = mlBox.width() * mlBox.height()
        val filled = occupancy >= CAPTURE_MIN_OCCUPANCY

        // 1. CENTER -- checked first, every tick, before anything else.
        // attemptCenteringCorrection() already owns the real hardware
        // safety rules (single-axis-only BLE commands, tilt mechanical-
        // limit budget, revert-on-overshoot) and is a safe no-op once
        // within CENTERING_DEADBAND, so this costs nothing once centered.
        if (!centered) {
            // No attempt cap here: this is the continuous per-tick loop, not
            // a bounded one-shot sequence (that's centerThenCapture(), which
            // keeps its own ANGLE_CENTERING_MAX_ATTEMPTS). Passing the
            // default CENTERING_MAX_ATTEMPTS (20) here meant centering
            // permanently gave up after 20 ticks (a few seconds) with no
            // further movement or log for the rest of the item -- confirmed
            // live (2026-08-18): ring visibly off-center and unmoving across
            // repeated screenshots, zero BLE writes, zero log lines. Keep
            // retrying every tick until actually centered.
            if (rsc2.isReady && result != null) attemptCenteringCorrection(result, maxAttempts = Int.MAX_VALUE)
            setStatus("Centering ornament…", ready = false)
            return
        }

        // 2. ZOOM -- only once centered, one step at a time.
        if (!filled) {
            if (now - lastZoomChangeAt >= ZOOM_STEP_INTERVAL_MS) {
                val zoom = focusZoom.currentZoomRatio()
                val zoomRange = focusZoom.zoomRatioRange()
                val next = (zoom * ZOOM_STEP_RATIO).coerceAtMost(min(zoomRange.endInclusive, MAX_LIVE_ZOOM_RATIO))
                smoothZoomTo(next)
                focusTriggeredThisLevel = false
            }
            setStatus("Zooming in…", ready = false)
            return
        }

        // 3. Let the lens settle after the last zoom step before trusting
        // any focus verdict against it.
        if (now - lastZoomChangeAt < ZOOM_SETTLE_MS) {
            setStatus("Zooming in…", ready = false)
            return
        }

        // 4. FOCUS -- one decisive trigger per zoom level.
        if (!focusTriggeredThisLevel) {
            focusTriggeredThisLevel = true
            focusZoom.triggerAutoFocus()
            setStatus("Focusing…", ready = false)
            return
        }
        val afState = focusZoom.afState.value
        if (!focusZoom.isFocusLocked(afState) || latestSharpness < SHARPNESS_THRESHOLD) {
            setStatus("Focusing…", ready = false)
            return
        }

        // 5. Everything green together -- click.
        setStatus("Ready. Capturing…", ready = true)
        captureJewel()
    }

    /** ML Kit detected-object box (upright-normalized, same space the
     * on-screen overlay already trusts) that actually contains gold/warm
     * MaterialDetector points -- NOT just the largest box, and NEVER a
     * non-gold fallback. Every consumer of this function (the arm gate via
     * detectedNow(), zoom-climb occupancy, the 75%-occupancy hard capture
     * gate, centering) is gold-exclusive by construction: they all read
     * this one function.
     *
     * Real bug found live (2026-08-18), in two parts:
     * 1. A small gold ring placed on/beside a large blue display box -- ML
     *    Kit's generic (color-blind) object detector reported the BOX as a
     *    detected object too, and being much larger than the ring, the old
     *    "just pick the biggest box" heuristic always won with the box.
     *    Every downstream consumer then chased the wrong object: coverage
     *    stayed near zero, centering never converged, capture never fired.
     * 2. The FIRST fix only made this function PREFER a gold box, still
     *    falling back to the largest non-gold box when no gold overlap
     *    existed that tick. That fallback is exactly how the pipeline could
     *    still arm/climb-zoom/report high occupancy against the box (or any
     *    other ML Kit object) whenever gold momentarily had no overlap --
     *    confirmed live: occupancy read 47-55% and coverageOk=true while
     *    the actual ring had already walked out of frame entirely. Per
     *    explicit correction ("gold is not the priority... investigate"),
     *    removed the fallback: this now returns null, not a substitute
     *    object, whenever there's no real gold evidence. Every caller
     *    already fails closed on null (meetsHardCaptureRules, the centering
     *    "lost the ornament" branch, etc.) -- that fail-closed behavior is
     *    exactly correct here: better to stall/re-search than to
     *    center/zoom/capture against the wrong object. */
    private fun bestObjectBox(): RectF? = bestGoldObjectBox()

    /** Same ML Kit box selection as bestObjectBox(), but returns null
     * (never a fallback) when no candidate box actually contains gold/warm
     * MaterialDetector points this tick. Use this, never bestObjectBox(),
     * anywhere that must never target a non-gold region -- currently just
     * updateTrackingRegionFor() (continuous AF/AE steering), per explicit
     * rule: focus tracks gold ONLY, always, never a generic ML Kit object
     * (a box lid, a hand, a shadow) even as a last-resort fallback. */
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
        // Spatial continuity: once locked onto an object, only candidates
        // near its last-known position are eligible -- a real showroom has
        // OTHER real gold jewellery in it (display cases, other pieces),
        // and pure density can legitimately favor one of those over the
        // item actually in the capture box the instant the gimbal drifts
        // even slightly. Confirmed live (2026-08-18): with the attempt cap
        // removed, centering kept "succeeding" against whatever gold
        // cluster scored highest each tick, walked the gimbal off the ring
        // in the capture box and onto full display cases across the room,
        // several tilt-steps away, with the RSC2 too dumb to know the
        // difference -- it was still "centering," just on the wrong thing.
        // MAX_TARGET_JUMP is generous (half the frame) so real tracking of
        // an object moving/zooming tick-to-tick is never blocked, but a
        // jump across the whole room is rejected -- return null (lost) so
        // the caller's existing lost-target recovery handles it, rather
        // than silently re-seeding onto something else.
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

    /** Continuously steers the AF/AE tracking region at wherever the GOLD
     * ornament currently is -- called every tick once armed, including
     * while the gimbal is mid-move, so continuous AF follows the object
     * through motion instead of losing it and having to re-search once the
     * gimbal stops.
     *
     * NON-NEGOTIABLE: focus tracks gold only, always. Prefers a gold-
     * verified ML Kit box (bestGoldObjectBox()), falls back to
     * MaterialDetector's own bounds (also gold-derived, never a generic
     * object), and if NEITHER has gold evidence this tick, does nothing --
     * holds the last good AF region rather than ever steering focus onto
     * an unverified/non-gold area (a display box, a hand, a shadow). */
    private fun updateTrackingRegionFor(result: MaterialDetector.Result?) {
        val box = bestGoldObjectBox()
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
        focusZoom.updateTrackingRegion(cx, cy)
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
     * staff decision) skips it. Fails closed (returns false) whenever ML
     * Kit hasn't found a box, since occupancy can't be verified without one. */
    private fun meetsHardCaptureRules(): Boolean {
        if (rsc2.isReady && rsc2.isMoving) return false
        val box = bestObjectBox() ?: return false
        val occupancy = box.width() * box.height()
        if (occupancy < CAPTURE_MIN_OCCUPANCY) return false
        val cx = (box.left + box.right) / 2f
        val cy = (box.top + box.bottom) / 2f
        return abs(cx - 0.5f) <= CENTERING_DEADBAND && abs(cy - 0.5f) <= CENTERING_DEADBAND
    }

    /** Hybrid detection check: true if EITHER signal sees something --
     * ML Kit's real object box, or MaterialDetector's colour/contrast
     * heuristic. Using both (not just MaterialDetector alone) is what lets
     * this arm/hunt correctly for silver, which MaterialDetector's
     * gold-hue heuristic under-detects. */
    private fun detectedNow(): Boolean = (latestMaterial?.material == true) || bestObjectBox() != null

    /** Active gimbal search for MAIN, used only once nothing has been
     * detected at all for HUNT_GRACE_MS -- rather than just waiting
     * indefinitely for the operator to reposition the item under a fixed
     * camera. Deterministic sweep order -- always scans the bottom, never
     * level or up: an ornament sits on the base, never in the air or on a
     * wall, so once tilted down the sweep stays down through the entire
     * pan search and only returns to level at the very end (GIVE_UP):
     *   1. SCAN_DOWN -- tilt down from level, budget-limited (TILT_MS_LIMIT)
     *   2. SCAN_LEFT -- pan left from center, STILL TILTED DOWN, budget-limited (HUNT_PAN_SWEEP_MAX_MS)
     *   3. RETURN_PAN -- back to center pan, still tilted down
     *   4. SCAN_RIGHT -- pan right from center, still tilted down, same budget
     *   5. GIVE_UP -- undo tilt AND pan, return home, let the operator reposition manually
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
                    // Stays tilted down -- deliberately no return-to-level
                    // here, the ornament is always on the base, never in
                    // the air or on a wall, so the pan sweep below scans
                    // the bottom the whole way through, not the middle.
                    huntPhase = HuntPhase.SCAN_LEFT
                    huntPhaseMsSpent = 0
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
                // Undoes whatever net pan/tilt the sweep left behind -- pan
                // should already be ~0 after RETURN_PAN, but tilt has been
                // held down since SCAN_DOWN (never returned to level
                // between phases, see this function's doc comment), so
                // this is the first point tilt gets undone.
                undoCenteringThenAdvance {
                    setStatus("Not found — reposition the ornament", ready = false)
                }
            }
        }
    }

    private fun huntStatusText(): String = when (huntPhase) {
        HuntPhase.SCAN_DOWN -> "Searching below…"
        HuntPhase.SCAN_LEFT -> "Searching below-left…"
        HuntPhase.RETURN_PAN -> "Returning to center (still below)…"
        HuntPhase.SCAN_RIGHT -> "Searching below-right…"
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

        // Safety check FIRST: if the last nudge this function issued was
        // followed by the ornament vanishing entirely (visible right
        // before that move, gone now), that move overshot it out of frame.
        // Undo just that one nudge and prefer the OTHER axis on the next
        // attempt, rather than continuing to push the axis that just lost
        // it. "What works" pattern per live testing: one axis at a time,
        // revert on loss, try the other axis next.
        if (lastCenterAxis != CenterAxis.NONE && bestObjectBox() == null && result.bounds == null) {
            centeringAttempts += 1
            val axis = lastCenterAxis
            val sign = lastCenterSign
            val durMs = lastCenterDurationMs
            Log.i(TAG, "centering nudge lost the ornament -- reverting axis=$axis sign=$sign durMs=$durMs")
            centerAvoidAxis = axis
            lastCenterAxis = CenterAxis.NONE
            setStatus("Centering ornament…", ready = false)
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

        val mlBox = bestObjectBox()
        val cx: Float
        val cy: Float
        if (mlBox != null) {
            cx = (mlBox.left + mlBox.right) / 2f
            cy = (mlBox.top + mlBox.bottom) / 2f
        } else {
            val bounds = result.bounds ?: return false
            cx = (bounds.x0 + bounds.x1) / 2f
            cy = (bounds.y0 + bounds.y1) / 2f
        }
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
                    Log.w(TAG, "centering: tilt budget exhausted (ms=$centeringTiltMs) and pan not needed -- giving up this round")
                    lastCenterAxis = CenterAxis.NONE
                    return false
                }
            }
        }
        // Pan had no equivalent budget cap at all until now -- with the
        // per-tick attempt cap also removed (see tickJewel's call site),
        // that let a target-switch onto a distant gold cluster (fixed
        // separately via MAX_TARGET_JUMP in bestGoldObjectBox()) walk pan
        // arbitrarily far before MAX_TARGET_JUMP could reject it. Same
        // pattern as tilt: exhausted budget falls back to the other axis if
        // it still needs correcting, else gives up this round rather than
        // pushing further.
        if (choosePan) {
            val panDurMs = centeringDurationFor(abs(dx))
            val panSign = if (dx > 0) 1 else -1
            if (abs(centeringPanMs + panSign * panDurMs) > PAN_MS_LIMIT) {
                if (needsTilt) {
                    choosePan = false
                } else {
                    Log.w(TAG, "centering: pan budget exhausted (ms=$centeringPanMs) and tilt not needed -- giving up this round")
                    lastCenterAxis = CenterAxis.NONE
                    return false
                }
            }
        }
        centeringAttempts += 1
        setStatus("Centering ornament…", ready = false)
        if (choosePan) {
            // Object right-of-center (dx>0) -> pan camera right to bring it in.
            // axis3 ABOVE center = the "right" direction. Duration scales
            // with how far off it is -- see centeringDurationFor().
            val sign = if (dx > 0) 1 else -1
            val durMs = centeringDurationFor(abs(dx))
            centeringPanMs += sign * durMs.toInt()
            lastCenterAxis = CenterAxis.PAN
            lastCenterSign = sign
            lastCenterDurationMs = durMs.toInt()
            val panAxis = DumlProtocol.AXIS_CENTER + sign * CENTERING_DEFLECTION
            Log.i(TAG, "centering nudge #$centeringAttempts (pan) dx=$dx dy=$dy pan=$panAxis durMs=$durMs")
            rsc2.moveOut(axis3 = panAxis, durationMs = durMs) {}
        } else {
            // Object low-in-frame (dy>0, y grows downward) -> tilt camera
            // down. axis1 ABOVE center = look up (confirmed live).
            val sign = if (dy > 0) -1 else 1
            centeringTiltMs += sign * tiltDurMs.toInt()
            lastCenterAxis = CenterAxis.TILT
            lastCenterSign = sign
            lastCenterDurationMs = tiltDurMs.toInt()
            val tiltAxis = DumlProtocol.AXIS_CENTER + sign * CENTERING_DEFLECTION
            Log.i(TAG, "centering nudge #$centeringAttempts (tilt) dx=$dx dy=$dy tilt=$tiltAxis durMs=$tiltDurMs")
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

    /** Loads the persisted center-drift reference (SharedPreferences,
     * survives app kill/relaunch) -- "remember center permanently". Called
     * once from onCreate. If nothing was ever saved (first run after this
     * feature existed), defaults to 0 -- treats whatever position the
     * gimbal physically starts this session at as the reference, which is
     * correct the first time since that's exactly what a fresh manual
     * recenter followed by a relaunch means. */
    private fun loadCenterDrift() {
        centeringPanMs = prefs.getInt("center_drift_pan_ms", 0)
        centeringTiltMs = prefs.getInt("center_drift_tilt_ms", 0)
        lastPersistedPanMs = centeringPanMs
        lastPersistedTiltMs = centeringTiltMs
        Log.i(TAG, "loaded persisted center drift: pan=$centeringPanMs tilt=$centeringTiltMs")
    }

    /** Flushes centeringPanMs/TiltMs to prefs if either changed since the
     * last flush. Called from tickRunnable (every TICK_INTERVAL_MS) rather
     * than at each individual mutation site -- there are many (legacy hunt/
     * centering AND VisionServoController's applyServoCommand) and periodic
     * flushing is simpler and safe: at worst one tick's drift (~150ms) is
     * lost on an app kill, not the whole session's. */
    private fun persistCenterDriftIfChanged() {
        if (centeringPanMs == lastPersistedPanMs && centeringTiltMs == lastPersistedTiltMs) return
        lastPersistedPanMs = centeringPanMs
        lastPersistedTiltMs = centeringTiltMs
        prefs.edit()
            .putInt("center_drift_pan_ms", centeringPanMs)
            .putInt("center_drift_tilt_ms", centeringTiltMs)
            .apply()
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
        val start = focusZoom.currentZoomRatio()
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
                focusZoom.setZoomRatio(start + (target - start) * eased)
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

    private fun captureJewel() {
        captureFullRes { bytes ->
            if (bytes == null) {
                setStatus("Capture failed — retrying", ready = false)
                return@captureFullRes
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
            val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
            val raw = bmp?.let { SharpnessAnalyzer.scoreBitmapRaw(it) }
            Log.i(TAG, "jewel capture fullRes sharpness raw=$raw size=${bmp?.width}x${bmp?.height} liveSharp=$latestSharpness")
            bmp?.recycle()

            jewelCaptureRetries = 0
            jewelJpeg = bytes
            showCapturePreview(
                bytes,
                onProceed = { onMainCaptureAccepted() },
                onRetake = { retakeJewel() },
                onCancel = { cancelItem() }
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
        if (!rsc2.isReady) {
            inAngleSequence = false
            resetForNewItem(Phase.TAG)
            return
        }
        inAngleSequence = true
        promptForSideProfile("Turn the ornament to show a SIDE profile, then tap READY") {
            centerThenCapture { captureAngle1() }
        }
    }

    /** Shows the instruction + big READY button and waits for the staff tap
     * before calling [onReady] -- no auto-timeout fire here, unlike the old
     * pan-sweep gate. The staff decides when the piece is actually
     * positioned; nothing should capture before that. */
    private fun promptForSideProfile(instruction: String, onReady: () -> Unit) {
        setStatus(instruction, ready = false)
        showReadyButton {
            centeringAttempts = 0
            angleZoomRounds = 0
            // Re-arms continuous AF as the baseline for this side's
            // tracking -- the MAIN capture's final triggerAutoFocus() lock
            // (or this same side's own, on a retake) does not resume
            // continuous scanning by itself.
            focusZoom.startContinuousTracking()
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
        val result = latestMaterial
        // Continuous tracking follows the object through every nudge this
        // loop issues, including while the gimbal is physically still
        // moving from the last one -- meetsHardCaptureRules() (via
        // rsc2.isMoving) is what actually blocks capture during motion,
        // not this call; this just keeps AF/AE aimed at the right place
        // the whole time so there's nothing to re-acquire once it stops.
        updateTrackingRegionFor(result)
        if (result != null && result.material &&
            attemptCenteringCorrection(result, ANGLE_CENTERING_MAX_ATTEMPTS)) {
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
            val zoom = focusZoom.currentZoomRatio()
            val zoomRange = focusZoom.zoomRatioRange()
            val next = (zoom * ZOOM_STEP_RATIO).coerceAtMost(min(zoomRange.endInclusive, MAX_LIVE_ZOOM_RATIO))
            if (next > zoom + 0.01f) {
                angleZoomRounds += 1
                setStatus("Zooming in…", ready = false)
                smoothZoomTo(next) {
                    handler.postDelayed({ centerThenCapture(onCentered) }, ZOOM_SETTLE_MS)
                }
                return
            }
        }
        focusZoom.triggerAutoFocus()
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
                val present = result?.material == true
                val focusLocked = focusZoom.isFocusLocked(focusZoom.afState.value)
                val sharpEnough = latestSharpness >= SHARPNESS_THRESHOLD
                val now = System.currentTimeMillis()
                if (present && focusLocked && sharpEnough) {
                    angleStableStreak += 1
                    if (angleStableStreak >= ANGLE_STABLE_TICKS) {
                        setStatus("Holding steady…", ready = true)
                        onDetected()
                        return
                    }
                } else {
                    angleStableStreak = 0
                }
                if (now >= deadline) {
                    Log.w(TAG, "waitForStableFrame forced after timeout present=$present focusLocked=$focusLocked sharp=$latestSharpness")
                    onDetected()
                    return
                }
                handler.postDelayed(this, 150L)
            }
        }
        handler.post(check)
    }

    private fun captureAngle1() {
        setStatus("Capturing angle 1…", ready = false)
        focusZoom.triggerAutoFocus()
        handler.postDelayed({
            captureFullRes { bytes ->
                Log.i(TAG, "captureAngle1 result bytes=${bytes?.size}")
                onAngle1Captured(bytes)
            }
        }, 400L)
    }

    private fun onAngle1Captured(bytes: ByteArray?) {
        if (bytes == null) {
            setStatus("Angle 1 capture failed — retrying", ready = false)
            captureAngle1()
            return
        }
        showCapturePreview(
            bytes,
            onProceed = {
                angle1Jpeg = bytes
                promptForSideProfile("Turn the ornament to show the OTHER side profile, then tap READY") {
                    centerThenCapture { captureAngle2() }
                }
            },
            onRetake = { captureAngle1() },
            onCancel = { cancelItem() }
        )
    }

    private fun captureAngle2() {
        setStatus("Capturing angle 2…", ready = false)
        focusZoom.triggerAutoFocus()
        handler.postDelayed({
            captureFullRes { bytes ->
                Log.i(TAG, "captureAngle2 result bytes=${bytes?.size}")
                onAngle2Captured(bytes)
            }
        }, 400L)
    }

    private fun onAngle2Captured(bytes: ByteArray?) {
        if (bytes == null) {
            setStatus("Angle 2 capture failed — retrying", ready = false)
            captureAngle2()
            return
        }
        showCapturePreview(
            bytes,
            onProceed = {
                angle2Jpeg = bytes
                setStatus("Returning to center…", ready = false)
                // Undoes the net tilt/pan correction accumulated across
                // MAIN + angle1 + angle2's centering nudges in one shot, so
                // the gimbal starts the next item from true center rather
                // than wherever the last item's corrections left it.
                undoCenteringThenAdvance {
                    inAngleSequence = false
                    resetForNewItem(Phase.TAG)
                }
            },
            onRetake = { captureAngle2() },
            onCancel = { cancelItem() }
        )
    }

    private fun forceCaptureCurrentPhase() {
        when (phase) {
            Phase.JEWEL -> captureJewel()
            Phase.TAG -> captureFullRes { bytes ->
                if (bytes != null) {
                    tagJpeg = bytes
                    showCapturePreview(
                        bytes,
                        onProceed = { uploadCapturedSet() },
                        onRetake = { retakeTag() },
                        onCancel = { cancelItem() }
                    )
                }
            }
            Phase.UPLOADING -> {}
        }
    }

    // ---------------------------------------------------------------- Capture preview

    /** Shows the just-captured photo full-screen with Retake/Cancel item
     * buttons and a 5s auto-continue countdown -- gives the operator a
     * real chance to catch a bad frame before it's used, matching
     * capture.html's own "Best frame selected · auto-proceeding in 3 sec"
     * preview step. */
    private fun showCapturePreview(
        jpeg: ByteArray,
        onProceed: () -> Unit,
        onRetake: () -> Unit,
        onCancel: () -> Unit,
        requireManualConfirm: Boolean = false
    ) {
        val bitmap = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size)
        if (bitmap == null) {
            // Decode failed -- don't show a blank/stale ImageView with the
            // live camera visible behind it looking like "the preview
            // didn't update". Skip straight to onProceed instead.
            Log.e(TAG, "Failed to decode captured JPEG for preview (${jpeg.size} bytes)")
            onProceed()
            return
        }
        previewShowing = true
        // Actually hide the live camera surface, not just draw over it --
        // a translucent overlay alone left the feed visibly bleeding
        // through underneath what was supposed to be a frozen photo.
        binding.previewView.visibility = View.INVISIBLE
        binding.boundsOverlay.update(emptyList(), 0, 0, 0)
        // Reset any pinch-zoom/pan left over from inspecting the LAST
        // preview -- otherwise a new photo could open already zoomed in.
        binding.previewImage.scaleX = 1f
        binding.previewImage.scaleY = 1f
        binding.previewImage.translationX = 0f
        binding.previewImage.translationY = 0f
        binding.previewImage.setImageBitmap(bitmap)
        binding.previewOverlay.visibility = View.VISIBLE

        binding.previewRetakeButton.setOnClickListener {
            hideCapturePreview()
            onRetake()
        }
        binding.previewContinueButton.setOnClickListener {
            hideCapturePreview()
            onProceed()
        }
        binding.previewCancelButton.setOnClickListener {
            hideCapturePreview()
            onCancel()
        }

        previewCountdownRunnable?.let { handler.removeCallbacks(it) }
        if (requireManualConfirm) {
            binding.previewCountdown.text = "Still soft after retries — tap Retake"
            previewCountdownRunnable = null
        } else {
            var secondsLeft = 5
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
        previewCountdownRunnable?.let { handler.removeCallbacks(it) }
        previewCountdownRunnable = null
        binding.previewOverlay.visibility = View.GONE
        binding.previewView.visibility = View.VISIBLE
        previewShowing = false
    }

    /** Discards the jewel shot and re-arms the JEWEL pipeline from
     * scratch, staying in this session (not returning to the browser). */
    private fun retakeJewel() {
        jewelJpeg = null
        angle1Jpeg = null
        angle2Jpeg = null
        inAngleSequence = false
        hideReadyButton()
        armed = false
        stepFocusAttempts = 0
        maxUsableZoom = Float.MAX_VALUE
        latestMaterial = null
        autoFired = false
        armedAt = System.currentTimeMillis()
        lastZoomChangeAt = 0L
        focusTriggeredThisLevel = false
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
        huntPhase = HuntPhase.SCAN_DOWN
        huntPhaseMsSpent = 0
        huntStartedAt = 0L
        latestObjectBoxesUpright = emptyList()
        focusZoom.setZoomRatio(1f)
        setStatus("Center the ornament, front side up…", ready = false)
    }

    /** Discards the tag shot only -- the jewel shot already captured
     * stays, no need to redo it. */
    private fun retakeTag() {
        tagJpeg = null
        tagCodeHistory = mutableListOf()
        stableTagCode = null
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
        hideReadyButton()
        // stopAndReturnToCenter() only halts in-flight motion (a neutral
        // frame) -- it does NOT undo accumulated pan/tilt drift, unlike the
        // normal angle2-completion path. "Job done = return to center"
        // applies here too: undo the real drift, THEN stop/reset.
        rsc2.stopAndReturnToCenter()
        undoCenteringThenAdvance {
            if (launchedFromBrowser) {
                finish()
            } else {
                resetForNewItem(Phase.JEWEL)
            }
        }
    }

    private fun captureFullRes(onResult: (ByteArray?) -> Unit) {
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
        if (angle1Jpeg != null && angle2Jpeg != null) uploadMulti() else uploadPair()
    }

    private fun uploadMulti() {
        val main = jewelJpeg
        val angle1 = angle1Jpeg
        val angle2 = angle2Jpeg
        val tagCode = stableTagCode
        if (main == null || angle1 == null || angle2 == null || tagCode == null) {
            setStatus("Missing photo — retake", ready = false)
            resetForNewItem(Phase.JEWEL)
            return
        }
        phase = Phase.UPLOADING
        setStatus("Uploading 3-angle set…", ready = false)
        val serverUrl = prefs.getString("server_url", "") ?: ""
        val staffName = prefs.getString("staff_name", "") ?: ""
        if (serverUrl.isBlank()) {
            Toast.makeText(this, "Set the capture server URL in Settings first", Toast.LENGTH_LONG).show()
            showSettingsDialog()
            resetForNewItem(Phase.JEWEL)
            return
        }
        lifecycleScope.launch {
            val result = try {
                UploadClient.saveMulti(serverUrl, tagCode, staffName, main, angle1, angle2)
            } catch (e: Exception) {
                Log.e(TAG, "Multi-angle upload failed", e)
                null
            }
            if (result == null) {
                Toast.makeText(this@MainActivity, "Upload failed — check server URL/network", Toast.LENGTH_LONG).show()
                resetForNewItem(Phase.JEWEL)
                return@launch
            }
            when {
                result.ok -> showItemSavedPopup(tagCode)
                result.duplicate -> confirmOverrideAndRetry("Duplicate tag $tagCode — save anyway?") { overrideDup ->
                    retryUploadMulti(tagCode, staffName, main, angle1, angle2, overrideDuplicate = overrideDup)
                }
                result.blurry -> confirmOverrideAndRetry("A photo in the set looked blurry — save anyway?") { overrideBlur ->
                    retryUploadMulti(tagCode, staffName, main, angle1, angle2, overrideBlur = overrideBlur)
                }
                result.notVisible -> confirmOverrideAndRetry("Jewellery not clearly visible — save anyway?") { overrideVis ->
                    retryUploadMulti(tagCode, staffName, main, angle1, angle2, overrideVisibility = overrideVis)
                }
                else -> {
                    Toast.makeText(this@MainActivity, "Save failed: ${result.error}", Toast.LENGTH_LONG).show()
                    resetForNewItem(Phase.JEWEL)
                }
            }
        }
    }

    private fun retryUploadMulti(
        tagCode: String, staffName: String, main: ByteArray, angle1: ByteArray, angle2: ByteArray,
        overrideDuplicate: Boolean = false, overrideBlur: Boolean = false, overrideVisibility: Boolean = false
    ) {
        lifecycleScope.launch {
            val result = try {
                UploadClient.saveMulti(
                    prefs.getString("server_url", "") ?: "", tagCode, staffName, main, angle1, angle2,
                    overrideDuplicate, overrideBlur, overrideVisibility
                )
            } catch (e: Exception) {
                null
            }
            if (result?.ok == true) {
                showItemSavedPopup(tagCode)
            } else {
                Toast.makeText(this@MainActivity, "Save failed: ${result?.error}", Toast.LENGTH_LONG).show()
                resetForNewItem(Phase.JEWEL)
            }
        }
    }

    private fun uploadPair() {
        val jewel = jewelJpeg
        val tag = tagJpeg
        val tagCode = stableTagCode
        if (jewel == null || tag == null || tagCode == null) {
            setStatus("Missing photo — retake", ready = false)
            resetForNewItem(Phase.JEWEL)
            return
        }
        phase = Phase.UPLOADING
        setStatus("Uploading…", ready = false)
        val serverUrl = prefs.getString("server_url", "") ?: ""
        val staffName = prefs.getString("staff_name", "") ?: ""
        if (serverUrl.isBlank()) {
            Toast.makeText(this, "Set the capture server URL in Settings first", Toast.LENGTH_LONG).show()
            showSettingsDialog()
            resetForNewItem(Phase.JEWEL)
            return
        }
        lifecycleScope.launch {
            val result = try {
                UploadClient.savePair(serverUrl, tagCode, staffName, jewel, tag)
            } catch (e: Exception) {
                Log.e(TAG, "Upload failed", e)
                null
            }
            if (result == null) {
                Toast.makeText(this@MainActivity, "Upload failed — check server URL/network", Toast.LENGTH_LONG).show()
                resetForNewItem(Phase.JEWEL)
                return@launch
            }
            when {
                result.ok -> {
                    Toast.makeText(this@MainActivity, "Saved: $tagCode", Toast.LENGTH_SHORT).show()
                    finishOrResetForNewItem()
                }
                result.duplicate -> confirmOverrideAndRetry("Duplicate tag $tagCode — save anyway?") { overrideDup ->
                    retryUpload(tagCode, staffName, jewel, tag, overrideDuplicate = overrideDup)
                }
                result.blurry -> confirmOverrideAndRetry("Jewel photo looked blurry — save anyway?") { overrideBlur ->
                    retryUpload(tagCode, staffName, jewel, tag, overrideBlur = overrideBlur)
                }
                result.notVisible -> confirmOverrideAndRetry("Jewellery not clearly visible — save anyway?") { overrideVis ->
                    retryUpload(tagCode, staffName, jewel, tag, overrideVisibility = overrideVis)
                }
                else -> {
                    Toast.makeText(this@MainActivity, "Save failed: ${result.error}", Toast.LENGTH_LONG).show()
                    resetForNewItem(Phase.JEWEL)
                }
            }
        }
    }

    private fun retryUpload(
        tagCode: String, staffName: String, jewel: ByteArray, tag: ByteArray,
        overrideDuplicate: Boolean = false, overrideBlur: Boolean = false, overrideVisibility: Boolean = false
    ) {
        lifecycleScope.launch {
            val result = try {
                UploadClient.savePair(
                    prefs.getString("server_url", "") ?: "", tagCode, staffName, jewel, tag,
                    overrideDuplicate, overrideBlur, overrideVisibility
                )
            } catch (e: Exception) {
                null
            }
            if (result?.ok == true) {
                Toast.makeText(this@MainActivity, "Saved: $tagCode", Toast.LENGTH_SHORT).show()
                finishOrResetForNewItem()
            } else {
                Toast.makeText(this@MainActivity, "Save failed: ${result?.error}", Toast.LENGTH_LONG).show()
                resetForNewItem(Phase.JEWEL)
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
            resetForNewItem(Phase.JEWEL)
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
            .setNegativeButton("Retake") { _, _ -> onChoice(false); resetForNewItem(Phase.JEWEL) }
            .setCancelable(false)
            .show()
    }

    // ---------------------------------------------------------------- State reset

    private fun resetForNewItem(next: Phase) {
        phase = next
        armed = next == Phase.TAG
        armedAt = System.currentTimeMillis()
        stepFocusAttempts = 0
        maxUsableZoom = Float.MAX_VALUE
        autoFired = false
        latestMaterial = null
        lastZoomChangeAt = 0L
        focusTriggeredThisLevel = false
        isZooming = false
        stallGraceAt = 0L
        readyStreak = 0
        jewelCaptureRetries = 0
        if (next == Phase.JEWEL) {
            // Normal completion already undid these via
            // undoCenteringThenAdvance() before calling here -- this is
            // just the defensive reset for abort/cancel paths that skip it.
            centeringPanMs = 0
            centeringTiltMs = 0
            centeringAttempts = 0
            lastCenterAxis = CenterAxis.NONE
            centerAvoidAxis = CenterAxis.NONE
            huntPhase = HuntPhase.SCAN_DOWN
            huntPhaseMsSpent = 0
            huntStartedAt = 0L
        }
        if (next == Phase.TAG) {
            barcodeAttempts = 0
            lastBarcodeCount = -1
            lastBarcodeError = null
        }
        if (next == Phase.JEWEL) {
            jewelJpeg = null
            angle1Jpeg = null
            angle2Jpeg = null
            tagJpeg = null
            tagCodeHistory = mutableListOf()
            stableTagCode = null
            focusZoom.setZoomRatio(1f)
        }
        setStatus(if (next == Phase.JEWEL) "Center the ornament, front side up…" else "Show the tag QR/barcode…", ready = false)
    }

    private fun setStatus(text: String, ready: Boolean) {
        binding.statusText.text = text
        binding.statusText.setBackgroundColor(
            if (ready) 0xB022C55E.toInt() else 0xB0000000.toInt()
        )
        val material = latestMaterial
        binding.debugText.text = if (phase == Phase.JEWEL) {
            val range = focusZoom.zoomRatioRange()
            "zoom=%.1fx range=[%.1f,%.1f] max=%.1f  coverage=%.3f  sharp=%.0f  af=%s".format(
                focusZoom.currentZoomRatio(),
                range.start, range.endInclusive, maxUsableZoom,
                material?.coverage ?: 0f,
                latestSharpness,
                afStateLabel(focusZoom.afState.value)
            )
        } else ""
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

    private fun showSettingsDialog() {
        val dialogBinding = DialogSettingsBinding.inflate(layoutInflater)
        dialogBinding.serverUrlInput.setText(prefs.getString("server_url", ""))
        dialogBinding.staffNameInput.setText(prefs.getString("staff_name", ""))
        AlertDialog.Builder(this)
            .setTitle(R.string.settings)
            .setView(dialogBinding.root)
            .setPositiveButton(R.string.save) { _, _ ->
                prefs.edit()
                    .putString("server_url", dialogBinding.serverUrlInput.text.toString().trim())
                    .putString("staff_name", dialogBinding.staffNameInput.text.toString().trim())
                    .apply()
            }
            .setNegativeButton(R.string.cancel, null)
            .setNeutralButton("RSC2 BLE test") { _, _ ->
                startActivity(Intent(this, BleDiagnosticsActivity::class.java))
            }
            .show()
    }

    override fun onDestroy() {
        super.onDestroy()
        handler.removeCallbacks(tickRunnable)
        rsc2.disconnect()
        try { unregisterReceiver(testMoveReceiver) } catch (_: IllegalArgumentException) {}
        try { unregisterReceiver(recenterReceiver) } catch (_: IllegalArgumentException) {}
        try { unregisterReceiver(nudgeReceiver) } catch (_: IllegalArgumentException) {}
        try { unregisterReceiver(zeroDriftReceiver) } catch (_: IllegalArgumentException) {}
    }
}
