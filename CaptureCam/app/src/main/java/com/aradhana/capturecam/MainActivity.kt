package com.aradhana.capturecam

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.hardware.camera2.CaptureResult
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
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
import kotlinx.coroutines.launch
import java.io.ByteArrayOutputStream
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

    private val prefs by lazy { getSharedPreferences("capturecam", MODE_PRIVATE) }
    private val handler = Handler(Looper.getMainLooper())
    private val barcodeScanner by lazy { BarcodeScanning.getClient() }

    // ---- Pipeline state (mirrors capture.html's module-level _quality* vars) ----
    private enum class Phase { JEWEL, TAG, UPLOADING }
    private var phase = Phase.JEWEL
    private var armed = false
    private var armedAt = 0L
    private var stepFocusAttempts = 0
    private var maxUsableZoom = Float.MAX_VALUE
    private var jewelJpeg: ByteArray? = null
    private var tagJpeg: ByteArray? = null
    private var tagCodeHistory = mutableListOf<String>()
    private var stableTagCode: String? = null
    private var autoFired = false
    private var lastAnalysisAt = 0L

    @Volatile private var latestMaterial: MaterialDetector.Result? = null
    @Volatile private var latestSharpness: Float = 0f
    @Volatile private var barcodeBusy = false
    @Volatile private var barcodeAttempts = 0
    @Volatile private var lastBarcodeCount = -1
    @Volatile private var lastBarcodeError: String? = null

    companion object {
        private const val TAG = "CaptureCam"
        private const val MIN_LIVE_COVERAGE = 0.10f
        private const val MAX_FOCUS_RETRIES = 2
        private const val ZOOM_BACKOFF_RATIO = 0.8f
        private const val ZOOM_STEP_RATIO = 1.15f
        private const val MAX_STALL_MS = 12_000L
        private const val TICK_INTERVAL_MS = 150L
        private const val SHARPNESS_THRESHOLD = 40f
        // Conservative live-zoom cap per the "physical distance should do
        // most of the framing" principle -- pushing digital/hybrid zoom
        // much past this loses detail the catalogue pipeline later wants.
        private const val MAX_LIVE_ZOOM_RATIO = 4.0f
    }

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) startCamera() else {
            Toast.makeText(this, "Camera permission is required", Toast.LENGTH_LONG).show()
            finish()
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
                imageProxy.close()
            }
            Phase.TAG -> {
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
                uploadPair()
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
                focusZoom.setZoomRatio((zoom * ZOOM_BACKOFF_RATIO).coerceAtLeast(1f))
                stepFocusAttempts = 0
            }
            setStatus("Re-centre the item…", ready = false)
            return
        }

        if (result.material && now - armedAt > MAX_STALL_MS) {
            // Absolute safety valve -- accept the best frame on offer
            // rather than cycling forever.
            captureJewel()
            return
        }

        val coverageOk = result.coverage >= MIN_LIVE_COVERAGE
        val afState = focusZoom.afState.value
        val focusLocked = focusZoom.isFocusLocked(afState)
        val focusFailed = focusZoom.isFocusFailed(afState)
        val sharpEnough = latestSharpness >= SHARPNESS_THRESHOLD

        if (coverageOk && focusLocked && sharpEnough) {
            setStatus("Ready. Capturing…", ready = true)
            captureJewel()
            return
        }

        val zoom = focusZoom.currentZoomRatio()
        val zoomRange = focusZoom.zoomRatioRange()
        val atZoomCeiling = zoom >= min(zoomRange.endInclusive, MAX_LIVE_ZOOM_RATIO) - 0.02f ||
            zoom >= maxUsableZoom - 0.02f

        if (!coverageOk) {
            // Too small to trust a focus verdict either way yet -- climb on
            // coverage alone, same reasoning as the web version's identical
            // branch (a crop this small would be judged on an upscaled,
            // artificially-softened analysis region).
            if (atZoomCeiling) {
                captureJewel() // nowhere left to climb -- accept what's on offer
                return
            }
            setStatus("Filling frame before capture…", ready = false)
            val next = (zoom * ZOOM_STEP_RATIO).coerceAtMost(min(zoomRange.endInclusive, MAX_LIVE_ZOOM_RATIO))
            focusZoom.setZoomRatio(next)
            focusZoom.triggerAutoFocus()
            stepFocusAttempts = 0
            return
        }

        // Coverage is trustworthy now -- this is where "never advance while
        // blurry" actually applies.
        if (afState == null) {
            // AF sweep not yet triggered/settled at this zoom.
            focusZoom.triggerAutoFocus()
            setStatus("Focusing…", ready = false)
            return
        }
        if (!focusLocked || !sharpEnough) {
            if (focusFailed || !sharpEnough) {
                stepFocusAttempts += 1
                if (stepFocusAttempts <= MAX_FOCUS_RETRIES) {
                    focusZoom.triggerAutoFocus()
                    setStatus("Refocusing…", ready = false)
                    return
                }
                // Retries exhausted -- step BACK, never forward into a level
                // even less likely to resolve.
                stepFocusAttempts = 0
                val backedOff = (zoom * ZOOM_BACKOFF_RATIO).coerceAtLeast(zoomRange.start)
                if (backedOff < zoom - 0.05f) {
                    maxUsableZoom = backedOff
                    focusZoom.setZoomRatio(backedOff)
                }
                focusZoom.triggerAutoFocus()
                setStatus("Refocusing…", ready = false)
                return
            }
            setStatus("Focusing…", ready = false)
            return
        }
    }

    private fun min(a: Float, b: Float) = if (a < b) a else b

    // ---------------------------------------------------------------- Capture + upload

    private fun captureJewel() {
        captureFullRes { bytes ->
            if (bytes == null) {
                setStatus("Capture failed — retrying", ready = false)
                return@captureFullRes
            }
            jewelJpeg = bytes
            resetForNewItem(Phase.TAG)
        }
    }

    private fun forceCaptureCurrentPhase() {
        when (phase) {
            Phase.JEWEL -> captureJewel()
            Phase.TAG -> captureFullRes { bytes ->
                if (bytes != null) { tagJpeg = bytes; uploadPair() }
            }
            Phase.UPLOADING -> {}
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
        if (next == Phase.TAG) {
            barcodeAttempts = 0
            lastBarcodeCount = -1
            lastBarcodeError = null
        }
        if (next == Phase.JEWEL) {
            jewelJpeg = null
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
            "zoom=%.1fx  coverage=%.3f  sharp=%.0f  af=%s".format(
                focusZoom.currentZoomRatio(),
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
            .show()
    }

    override fun onDestroy() {
        super.onDestroy()
        handler.removeCallbacks(tickRunnable)
    }
}
