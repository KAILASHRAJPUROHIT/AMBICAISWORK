package com.aradhana.capturecam

import android.Manifest
import android.content.Intent
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
import java.nio.ByteBuffer

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
    // RSC 2 3-angle workflow -- fails open to the existing single-image
    // flow when no gimbal is connected (spec rule 61: single-image mode
    // must not break just because the gimbal/calibration layer isn't
    // available). Fixed test deflections until real per-category
    // calibration profiles are wired in; axis3 avoided since its effect
    // isn't confirmed (see RSC2Controller's doc comment).
    private val rsc2 = RSC2Controller()
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
    private var readyStreak = 0
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
        private const val REQUIRED_READY_TICKS = 3
        // Fixed test values for the RSC 2 3-angle workflow -- NOT real
        // per-category calibration yet. Single-axis pan sweep (axis2,
        // confirmed on real hardware): center -> pan LEFT one step (angle 1)
        // -> pan RIGHT two steps, crossing back through center to the
        // mirrored right-side position (angle 2) -> pan LEFT one step,
        // returning to true center for the next item. "Step" is expressed
        // as a fixed deflection held for PAN_STEP_MS, not a calibrated
        // degree value -- these are velocity commands (see RSC2Controller),
        // so travelled angle is deflection x time, not a fixed number.
        private const val PAN_DEFLECTION = 260
        private const val PAN_LEFT_AXIS2 = DumlProtocol.AXIS_CENTER - PAN_DEFLECTION
        private const val PAN_RIGHT_AXIS2 = DumlProtocol.AXIS_CENTER + PAN_DEFLECTION
        private const val PAN_STEP_MS = 900L
        // Conservative live-zoom cap per the "physical distance should do
        // most of the framing" principle -- pushing digital/hybrid zoom
        // much past this loses detail the catalogue pipeline later wants.
        private const val MAX_LIVE_ZOOM_RATIO = 3.4f
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

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED
        ) {
            startCamera()
        } else {
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
        attemptGimbalConnect()
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
            resetForNewItem(Phase.JEWEL)
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
    }

    // ---------------------------------------------------------------- Camera setup

    private fun startCamera() {
        val providerFuture = ProcessCameraProvider.getInstance(this)
        providerFuture.addListener({
            cameraProvider = providerFuture.get()
            bindUseCases()
        }, ContextCompat.getMainExecutor(this))
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
        camera?.let { focusZoom.bind(it) }

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
                val result = MaterialDetector.analyse(imageProxy)
                latestMaterial = result
                latestSharpness = if (result.bounds != null) {
                    SharpnessAnalyzer.score(imageProxy, result.bounds)
                } else 0f

                val rotation = imageProxy.imageInfo.rotationDegrees
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
            when (phase) {
                Phase.JEWEL -> tickJewel()
                Phase.TAG -> tickTag()
                Phase.UPLOADING -> {}
            }
            handler.postDelayed(this, TICK_INTERVAL_MS)
        }
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

        if (!armed) {
            if (result == null || !result.material) {
                setStatus("Place the item in frame…", ready = false)
                return
            }
            armed = true
            armedAt = now
        }

        if (result == null || !result.material) {
            // Lost the piece -- likely walked out of frame on a zoom step
            // (digital/hybrid zoom on this class of lens is still centre-
            // anchored). Ease back to re-acquire rather than climbing
            // further on an empty frame.
            val zoom = focusZoom.currentZoomRatio()
            if (zoom > 1.05f) {
                smoothZoomTo((zoom * ZOOM_BACKOFF_RATIO).coerceAtLeast(1f))
                stepFocusAttempts = 0
                focusTriggeredThisLevel = false
            }
            setStatus("Re-centre the item…", ready = false)
            return
        }

        if (result.material && now - armedAt > MAX_STALL_MS) {
            // Absolute safety valve -- accept the best frame on offer rather
            // than cycling forever. This used to call captureJewel() with
            // zero regard for focus/sharpness at all, which is exactly how
            // a shot could come out blurred: if AF genuinely never
            // converges (low-texture surface, awkward angle), stall expiry
            // fired mid-scan and shuttered on whatever was live that
            // instant. Now it still gives up eventually, but only after one
            // last forced re-focus, and only accepts a plainly-soft frame
            // if that final attempt also failed.
            val relaxedSharp = latestSharpness >= SHARPNESS_THRESHOLD * 0.6f
            if (relaxedSharp) {
                captureJewel()
                return
            }
            if (stallGraceAt == 0L) {
                stallGraceAt = now
                focusZoom.triggerAutoFocus()
                setStatus("Focusing…", ready = false)
                return
            }
            if (now - stallGraceAt < 800L) {
                setStatus("Focusing…", ready = false)
                return
            }
            captureJewel()
            return
        }

        val zoom = focusZoom.currentZoomRatio()
        val zoomRange = focusZoom.zoomRatioRange()
        val atZoomCeiling = zoom >= min(zoomRange.endInclusive, MAX_LIVE_ZOOM_RATIO) - 0.02f ||
            zoom >= maxUsableZoom - 0.02f
        // At the ceiling, accept whatever coverage is on offer as "the best
        // framing available" -- but this must NOT mean skipping focus
        // verification. It previously called captureJewel() directly here,
        // which is exactly how a shot could come out both too-far-away AND
        // blurry at once: an item too small to ever cross MIN_LIVE_COVERAGE
        // within the zoom cap got captured with focus never even checked.
        // Folding the ceiling into coverageOk instead just changes what
        // "enough of the frame" means for THIS item; every capture still
        // goes through the same focusLocked + sharpEnough gate below.
        val coverageOk = result.coverage >= MIN_LIVE_COVERAGE || atZoomCeiling
        val zoomSettled = now - lastZoomChangeAt >= ZOOM_SETTLE_MS
        val afState = focusZoom.afState.value
        val focusLocked = focusZoom.isFocusLocked(afState)
        val focusFailed = focusZoom.isFocusFailed(afState)
        val sharpEnough = latestSharpness >= SHARPNESS_THRESHOLD

        if (coverageOk && zoomSettled && focusLocked && sharpEnough) {
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
            readyStreak = 0
            setStatus("Ready. Capturing…", ready = true)
            captureJewel()
            return
        }
        readyStreak = 0

        if (!coverageOk) {
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
            // Must also respect maxUsableZoom -- a level a previous backoff
            // already proved unfocusable. Without this the climb ignored
            // that ceiling entirely and marched straight back up to the
            // exact same problem zoom every time, failed focus again,
            // backed off again, forever: the "zooms in, zooms back out,
            // keeps cycling" loop.
            val climbCeiling = min(min(zoomRange.endInclusive, MAX_LIVE_ZOOM_RATIO), maxUsableZoom)
            val next = (zoom * ZOOM_STEP_RATIO).coerceAtMost(climbCeiling)
            smoothZoomTo(next)
            stepFocusAttempts = 0
            focusTriggeredThisLevel = false
            setStatus("Zooming in…", ready = false)
            return
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
            focusTriggeredThisLevel = true
            focusZoom.triggerAutoFocus()
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
                stepFocusAttempts += 1
                if (stepFocusAttempts <= MAX_FOCUS_RETRIES) {
                    // One more genuine, decisive attempt at this SAME zoom
                    // level (falls through to the focusTriggeredThisLevel
                    // branch above on the next tick).
                    focusTriggeredThisLevel = false
                    setStatus("Focusing…", ready = false)
                    return
                }
                // Retries exhausted -- step BACK, never forward into a level
                // even less likely to resolve.
                stepFocusAttempts = 0
                val backedOff = (zoom * ZOOM_BACKOFF_RATIO).coerceAtLeast(zoomRange.start)
                if (backedOff < zoom - 0.05f) {
                    maxUsableZoom = backedOff
                    smoothZoomTo(backedOff)
                }
                focusTriggeredThisLevel = false
                setStatus("Focusing…", ready = false)
                return
            }
            setStatus("Focusing…", ready = false)
            return
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
     */
    private fun onMainCaptureAccepted() {
        Log.i(TAG, "onMainCaptureAccepted: rsc2.isReady=${rsc2.isReady}")
        if (!rsc2.isReady) {
            inAngleSequence = false
            resetForNewItem(Phase.TAG)
            return
        }
        inAngleSequence = true
        setStatus("Moving to angle 1…", ready = false)
        Log.i(TAG, "moveOut angle1 pan=$PAN_LEFT_AXIS2")
        rsc2.moveOut(DumlProtocol.AXIS_CENTER, PAN_LEFT_AXIS2, PAN_STEP_MS) {
            Log.i(TAG, "moveOut angle1 arrived")
            captureAngle1()
        }
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
            setStatus("Angle 1 capture failed — returning and retrying", ready = false)
            rsc2.returnHome(DumlProtocol.AXIS_CENTER, PAN_LEFT_AXIS2, PAN_STEP_MS) { onMainCaptureAccepted() }
            return
        }
        angle1Jpeg = bytes
        setStatus("Returning to center…", ready = false)
        // MUST return home before moving out to angle 2 -- these are
        // velocity commands, not absolute positions (see RSC2Controller's
        // moveOut/returnHome doc). Skipping this left the gimbal drifted
        // for angle 2, and for the NEXT item's angle 1.
        rsc2.returnHome(DumlProtocol.AXIS_CENTER, PAN_LEFT_AXIS2, PAN_STEP_MS) {
            setStatus("Moving to angle 2…", ready = false)
            Log.i(TAG, "moveOut angle2 pan=$PAN_RIGHT_AXIS2 rsc2.isReady=${rsc2.isReady}")
            rsc2.moveOut(DumlProtocol.AXIS_CENTER, PAN_RIGHT_AXIS2, PAN_STEP_MS) {
                Log.i(TAG, "moveOut angle2 arrived")
                captureAngle2()
            }
        }
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
            setStatus("Angle 2 capture failed — returning and retrying", ready = false)
            rsc2.returnHome(DumlProtocol.AXIS_CENTER, PAN_RIGHT_AXIS2, PAN_STEP_MS) { onMainCaptureAccepted() }
            return
        }
        angle2Jpeg = bytes
        setStatus("Returning to main position…", ready = false)
        rsc2.returnHome(DumlProtocol.AXIS_CENTER, PAN_RIGHT_AXIS2, PAN_STEP_MS) {
            inAngleSequence = false
            resetForNewItem(Phase.TAG)
        }
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
        readyStreak = 0
        jewelCaptureRetries = 0
        latestObjectBoxesUpright = emptyList()
        focusZoom.setZoomRatio(1f)
        setStatus("Place the item in frame…", ready = false)
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
        rsc2.stopAndReturnToCenter()
        if (launchedFromBrowser) {
            finish()
        } else {
            resetForNewItem(Phase.JEWEL)
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
                result.ok -> {
                    Toast.makeText(this@MainActivity, "Saved 3-angle set: $tagCode", Toast.LENGTH_SHORT).show()
                    finishOrResetForNewItem()
                }
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
                Toast.makeText(this@MainActivity, "Saved 3-angle set: $tagCode", Toast.LENGTH_SHORT).show()
                finishOrResetForNewItem()
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
        setStatus(if (next == Phase.JEWEL) "Place the item in frame…" else "Show the tag QR/barcode…", ready = false)
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
    }
}
