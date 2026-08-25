package com.aradhana.capturecam

import android.graphics.BitmapFactory
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import kotlin.concurrent.thread
import kotlin.math.min
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock
import kotlin.math.roundToInt

/**
 * Lifecycle-safe production owner for the Sony PTP/IP session.
 *
 * The Activity owns the capture workflow; this class owns only transport,
 * persistent Live View, bounded reconnect, and serialized camera commands.
 * A healthy Sony source is declared only after a JPEG has decoded. Until
 * then MainActivity keeps CameraX as its operational fallback.
 */
class SonyProductionCamera(
    private val onFrame: (android.graphics.Bitmap) -> Unit,
    private val onAvailabilityChanged: (Boolean, String) -> Unit
) {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val stateLock = Any()

    @Volatile private var running = false
    @Volatile private var liveRunning = false
    @Volatile private var frameReady = false
    @Volatile private var connectInFlight = false
    private val commandLock = ReentrantLock()
    private val autofocusInFlight = AtomicBoolean(false)
    private val controlInFlight = AtomicBoolean(false)
    @Volatile private var controller: SonyPtpIpController? = null
    @Volatile private var captureController: SonyPtpIpController? = null
    @Volatile private var captureMode = false
    @Volatile private var captureConnectInFlight = false
    @Volatile private var desiredQualitySettings: SonyQualitySettings? = null
    @Volatile private var captureQualityVerified = false
    @Volatile private var controlTransition = false
    @Volatile private var latestFocusIndication: Int? = null
    private var finishCaptureRunnable: Runnable? = null
    private var generation = 0L
    private var reconnectAttempt = 0
    private var reconnectIncidentStartedAtMs = 0L
    private var liveSessionStartedAtMs = 0L
    private var reconnectRunnable: Runnable? = null
    private var cameraIp = ""
    private var sshUser = ""
    private var sshPassword = ""

    val isAvailable: Boolean
        get() = running && liveRunning && frameReady && controller?.isConnected == true

    fun currentZoomRatio(): Float =
        captureController?.takeIf { it.isConnected }?.zoomRatio()
            ?: controller?.zoomRatio() ?: 1f

    fun currentFocusIndication(): Int? = latestFocusIndication

    fun start(cameraIp: String, sshUser: String, sshPassword: String) {
        synchronized(stateLock) {
            if (running) return
            running = true
            this.cameraIp = cameraIp
            this.sshUser = sshUser
            this.sshPassword = sshPassword
            generation += 1L
            reconnectAttempt = 0
        }
        connectOnce(generation)
    }

    fun stop() {
        val old: SonyPtpIpController?
        synchronized(stateLock) {
            running = false
            liveRunning = false
            frameReady = false
            generation += 1L
            reconnectRunnable?.let(mainHandler::removeCallbacks)
            reconnectRunnable = null
            finishCaptureRunnable?.let(mainHandler::removeCallbacks)
            finishCaptureRunnable = null
            old = controller
            controller = null
            captureController?.disconnect()
            captureController = null
            captureQualityVerified = false
            captureMode = false
            controlTransition = false
        }
        old?.disconnect()
        onAvailabilityChanged(false, "Sony stopped")
    }

    private fun connectOnce(expectedGeneration: Long, preserveLastSonyFrame: Boolean = false) {
        synchronized(stateLock) {
            if (!running || generation != expectedGeneration || connectInFlight) return
            connectInFlight = true
            reconnectRunnable?.let(mainHandler::removeCallbacks)
            reconnectRunnable = null
        }
        if (!preserveLastSonyFrame) onAvailabilityChanged(false, "Connecting Sony…")
        thread(name = "SonyProductionConnect") {
            val candidate = SonyPtpIpController()
            val ok = candidate.connectBlocking(cameraIp, sshUser, sshPassword)
            synchronized(stateLock) { connectInFlight = false }
            if (!running || generation != expectedGeneration) {
                candidate.disconnect()
                return@thread
            }
            if (!ok) {
                candidate.disconnect()
                if (preserveLastSonyFrame) {
                    onAvailabilityChanged(false, "Sony renewal failed — phone fallback active")
                }
                scheduleReconnect("Sony handshake failed")
                return@thread
            }
            synchronized(stateLock) {
                controller?.disconnect()
                controller = candidate
            }
            startLiveLoop(candidate, expectedGeneration)
        }
    }

    private fun startLiveLoop(camera: SonyPtpIpController, expectedGeneration: Long) {
        camera.setLiveViewStreaming(true)
        liveRunning = true
        frameReady = false
        thread(name = "SonyProductionLiveView") {
            var failures = 0
            var firstFrame = true
            var lastLoggedFocusIndication: Int? = null
            var cadenceWindowStartedAt = SystemClock.elapsedRealtime()
            var cadenceFrames = 0
            while (running && liveRunning && generation == expectedGeneration &&
                controller === camera && camera.isConnected
            ) {
                // No proactive lease refresh here -- confirmed live
                // 2026-08-24 that it made things WORSE, not better.
                // refreshLiveViewLease() polls PTP property 0x9209, which
                // this exact file already documents (see startKeepAliveThread's
                // comment) as something the ZV-E10 II stops answering once
                // the remote session settles -- that constraint was
                // respected for the idle keepalive but NOT here. Calling it
                // put the camera's HTTP live-view producer into a ~13s
                // string of 503 Service Unavailable responses, which then
                // exhausted the pump's HTTP-only retry budget and forced a
                // full SSH/PTP re-handshake (another ~10s) -- a self-
                // inflicted ~23s outage every 30s, strictly worse than
                // just letting Sony's own ~45s natural close happen and
                // recover via a plain HTTP reopen on the same session.
                // SonyPtpIpController's pump now retries that HTTP-only
                // reopen patiently on its own; nothing here needs to
                // preempt it.
                val sample = camera.fetchLatestLiveViewSample()
                sample?.focusIndication?.let { focus ->
                    latestFocusIndication = focus
                    if (focus != lastLoggedFocusIndication) {
                        Log.i(TAG, "Sony AF indication=$focus frame=${sample.sequence}")
                        lastLoggedFocusIndication = focus
                    }
                }
                val bitmap = sample?.let {
                    BitmapFactory.decodeByteArray(it.jpeg, 0, it.jpeg.size)
                }
                if (bitmap == null) {
                    failures += 1
                    if (failures >= MAX_CONSECUTIVE_FRAME_FAILURES) {
                        Log.w(TAG, "Sony Live View unhealthy after $failures failures")
                        break
                    }
                    try { Thread.sleep(50L) } catch (_: InterruptedException) { break }
                    continue
                }
                failures = 0
                if (firstFrame) {
                    firstFrame = false
                    frameReady = true
                    reconnectAttempt = 0
                    reconnectIncidentStartedAtMs = 0L
                    liveSessionStartedAtMs = SystemClock.elapsedRealtime()
                    onAvailabilityChanged(true, "Sony live")
                }
                try {
                    onFrame(bitmap)
                } catch (e: Exception) {
                    Log.e(TAG, "Sony production frame consumer failed", e)
                }
                cadenceFrames += 1
                val cadenceNow = SystemClock.elapsedRealtime()
                val cadenceElapsed = cadenceNow - cadenceWindowStartedAt
                if (cadenceElapsed >= 5_000L) {
                    val fps = cadenceFrames * 1_000f / cadenceElapsed
                    // renderedFps alone can look healthy while the operator is
                    // watching seconds-old frames, so always log it next to the
                    // pump's source/dropped/age counters.
                    Log.i(
                        TAG,
                        "Sony Live View renderedFps=${"%.1f".format(fps)} " +
                            "jpegBytes=${sample.jpeg.size} " +
                            "ageMs=${camera.liveViewSampleAgeMs(sample)} ${camera.liveViewTelemetry()}"
                    )
                    cadenceWindowStartedAt = cadenceNow
                    cadenceFrames = 0
                }
                // No pacing sleep. fetchLatestLiveViewSample() already blocks
                // until a genuinely NEW frame exists, so this loop self-paces
                // to the camera's real cadence. Sleeping here would only make
                // the consumer slower than the source, which now costs dropped
                // frames rather than latency -- but there is no reason to pay
                // it at all.
            }
            camera.disconnect()
            val stillOwnsProductionSession = synchronized(stateLock) {
                if (controller === camera) {
                    controller = null
                    liveRunning = false
                    frameReady = false
                    true
                } else {
                    // A deliberate capture/control transition already
                    // detached this loop and may have installed its
                    // replacement. Never clear or reconnect over it.
                    false
                }
            }
            if (stillOwnsProductionSession && running && generation == expectedGeneration &&
                !captureMode && !controlTransition
            ) {
                val sessionAgeMs = liveSessionStartedAtMs.takeIf { it > 0L }
                    ?.let { SystemClock.elapsedRealtime() - it }
                Log.w(
                    TAG,
                    "Sony Live View lost; sessionAge=${sessionAgeMs?.let(::formatDuration) ?: "unknown"}"
                )
                // Without the old proactive lease-refresh path, EVERY loop
                // exit here now means the same thing that path's failure
                // used to: the pump exhausted its own patient HTTP-reopen
                // retries (SonyPtpIpController.LIVE_VIEW_MAX_REOPEN_FAILURES)
                // on what is very likely a temporary Sony-side hiccup, not a
                // genuinely dead camera -- a truly gone camera fails the
                // `camera.isConnected` check in this loop's own condition
                // instead. So always take the graceful path: keep showing
                // the last good frame and reconnect quickly, rather than
                // visibly flashing to the CameraX fallback UI for what is
                // usually a few-second blip.
                connectOnce(expectedGeneration, preserveLastSonyFrame = true)
            }
        }
    }

    private fun scheduleReconnect(reason: String) {
        synchronized(stateLock) {
            if (!running || captureMode || controlTransition || reconnectRunnable != null || connectInFlight) return
            liveRunning = false
            controller?.disconnect()
            controller = null
            val expectedGeneration = generation
            val delayMs = min(15_000L, 1_000L * (1L shl min(reconnectAttempt, 4)))
            if (reconnectIncidentStartedAtMs == 0L) {
                reconnectIncidentStartedAtMs = SystemClock.elapsedRealtime()
            }
            reconnectAttempt += 1
            val task = Runnable {
                synchronized(stateLock) { reconnectRunnable = null }
                connectOnce(expectedGeneration)
            }
            reconnectRunnable = task
            mainHandler.postDelayed(task, delayMs)
            Log.w(TAG, "$reason; reconnecting in ${delayMs}ms")
            if (reconnectAttempt == POWER_CONFIGURATION_HINT_ATTEMPT) {
                val outageMs = SystemClock.elapsedRealtime() - reconnectIncidentStartedAtMs
                Log.e(
                    TAG,
                    "Sony remains unreachable after ${formatDuration(outageMs)}. " +
                        "Camera-side hardwall required: Remote Shooting On; Power Save Start Time Off; " +
                        "Power Save by Monitor Does Not Link; USB Power Supply On with battery inserted. " +
                        "CaptureCam will keep retrying on phone fallback."
                )
            }
        }
    }

    private fun formatDuration(durationMs: Long): String {
        val totalSeconds = durationMs.coerceAtLeast(0L) / 1_000L
        val minutes = (totalSeconds / 60L).toString().padStart(2, '0')
        val seconds = (totalSeconds % 60L).toString().padStart(2, '0')
        return "$minutes:$seconds"
    }

    /** Takes a native Sony burst and returns the sharpest original full-resolution JPEG. */
    fun captureStill(onResult: (ByteArray?) -> Unit) {
        finishCaptureRunnable?.let(mainHandler::removeCallbacks)
        finishCaptureRunnable = null

        captureController?.takeIf { it.isConnected }?.let { camera ->
            captureOnSession(camera, onResult)
            return
        }

        val liveCamera: SonyPtpIpController
        val expectedGeneration: Long
        synchronized(stateLock) {
            if (!isAvailable || captureMode || captureConnectInFlight) {
                mainHandler.post { onResult(null) }
                return
            }
            liveCamera = controller ?: run {
                mainHandler.post { onResult(null) }
                return
            }
            expectedGeneration = generation
            captureMode = true
            captureConnectInFlight = true
            liveRunning = false
            frameReady = false
            controller = null
        }

        // The ZV-E10 II accepts one PTP command session at a time. Its command
        // responses remain serialized once the HTTP Live View stream starts,
        // even after that HTTP stream closes. A full-resolution shutter must
        // therefore reopen one fresh PTP session. Live View is restored after
        // the short capture-session idle window below.
        liveCamera.disconnect()
        thread(name = "SonyProductionCaptureConnect") {
            try { Thread.sleep(CAPTURE_REOPEN_SETTLE_MS) } catch (_: InterruptedException) { }
            val camera = SonyPtpIpController()
            val connected = camera.connectBlocking(cameraIp, sshUser, sshPassword, "CaptureCam-Capture")
            captureConnectInFlight = false
            if (!running || generation != expectedGeneration || !connected) {
                camera.disconnect()
                mainHandler.post { onResult(null) }
                finishCaptureMode(expectedGeneration)
                return@thread
            }
            captureController = camera
            captureQualityVerified = false
            captureOnSession(camera, onResult)
        }
    }

    private fun captureOnSession(camera: SonyPtpIpController, onResult: (ByteArray?) -> Unit) {
        thread(name = "SonyProductionCapture") {
            val bytes = commandLock.withLock {
                try {
                    val qualityOk = if (captureQualityVerified) {
                        true
                    } else {
                        val desired = desiredQualitySettings
                        (desired == null || camera.applyQualitySettings(desired)).also { ok ->
                            captureQualityVerified = ok
                            if (!ok) Log.e(TAG, "Sony capture blocked: quality hardwall verification failed")
                        }
                    }
                    if (!qualityOk) {
                        null
                    } else {
                        val burst = camera.triggerBurstTest(CAPTURE_BEST_OF_FRAMES)
                        val selected = burst.selectedImage
                        if (selected != null) {
                            Log.i(
                                TAG,
                                "Sony production best-of-${burst.requestedFrames}: " +
                                    "retrieved=${burst.retrievedFrames} selected=${burst.selectedFrameIndex} " +
                                    "scores=${burst.sharpnessScores.map { "%.1f".format(it) }}"
                            )
                            selected
                        } else {
                            Log.w(TAG, "Sony burst selection failed; taking one fail-safe still: ${burst.error}")
                            if (camera.triggerShutter()) camera.lastCapturedImage else null
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Sony still capture failed", e)
                    null
                }
            }
            mainHandler.post {
                scheduleFinishCaptureMode(generation)
                // Schedule before callback so a subsequent requested capture
                // can cancel this idle timer before starting its shutter.
                onResult(bytes)
            }
        }
    }

    /** Diagnostic hook for the same native burst/retrieval/scoring path used in production. */
    fun testBurst(
        frameCount: Int = 5,
        onResult: (SonyPtpIpController.BurstTestResult?) -> Unit
    ) {
        finishCaptureRunnable?.let(mainHandler::removeCallbacks)
        finishCaptureRunnable = null

        captureController?.takeIf { it.isConnected }?.let { camera ->
            burstOnSession(camera, frameCount, onResult)
            return
        }

        val liveCamera: SonyPtpIpController
        val expectedGeneration: Long
        synchronized(stateLock) {
            if (!isAvailable || captureMode || captureConnectInFlight) {
                mainHandler.post { onResult(null) }
                return
            }
            liveCamera = controller ?: run {
                mainHandler.post { onResult(null) }
                return
            }
            expectedGeneration = generation
            captureMode = true
            captureConnectInFlight = true
            liveRunning = false
            frameReady = false
            controller = null
        }

        liveCamera.disconnect()
        thread(name = "SonyProductionBurstConnect") {
            try { Thread.sleep(CAPTURE_REOPEN_SETTLE_MS) } catch (_: InterruptedException) { }
            val camera = SonyPtpIpController()
            val connected = camera.connectBlocking(cameraIp, sshUser, sshPassword, "CaptureCam-BurstTest")
            captureConnectInFlight = false
            if (!running || generation != expectedGeneration || !connected) {
                camera.disconnect()
                mainHandler.post { onResult(null) }
                finishCaptureMode(expectedGeneration)
                return@thread
            }
            captureController = camera
            captureQualityVerified = false
            burstOnSession(camera, frameCount, onResult)
        }
    }

    private fun burstOnSession(
        camera: SonyPtpIpController,
        frameCount: Int,
        onResult: (SonyPtpIpController.BurstTestResult?) -> Unit
    ) {
        thread(name = "SonyProductionBurst") {
            val result = commandLock.withLock {
                try {
                    val desired = desiredQualitySettings
                    val qualityOk = captureQualityVerified ||
                        (desired == null || camera.applyQualitySettings(desired)).also {
                            captureQualityVerified = it
                        }
                    if (qualityOk) camera.triggerBurstTest(frameCount) else null
                } catch (e: Exception) {
                    Log.e(TAG, "Sony burst test failed", e)
                    null
                }
            }
            mainHandler.post {
                scheduleFinishCaptureMode(generation)
                onResult(result)
            }
        }
    }

    private fun scheduleFinishCaptureMode(expectedGeneration: Long) {
        finishCaptureRunnable?.let(mainHandler::removeCallbacks)
        val task = Runnable { finishCaptureMode(expectedGeneration) }
        finishCaptureRunnable = task
        mainHandler.postDelayed(task, CAPTURE_BURST_IDLE_MS)
    }

    private fun finishCaptureMode(expectedGeneration: Long) {
        synchronized(stateLock) {
            finishCaptureRunnable?.let(mainHandler::removeCallbacks)
            finishCaptureRunnable = null
            captureController?.disconnect()
            captureController = null
            captureQualityVerified = false
            captureConnectInFlight = false
            captureMode = false
        }
        if (running && generation == expectedGeneration) connectOnce(expectedGeneration)
    }

    fun autofocus(
        normalizedX: Float = 0.5f,
        normalizedY: Float = 0.5f,
        onResult: (Boolean) -> Unit = {}
    ) {
        val camera = controller
        if (!isAvailable || camera == null || !camera.isConnected || captureMode || controlTransition) {
            mainHandler.post { onResult(false) }
            return
        }
        if (!autofocusInFlight.compareAndSet(false, true)) {
            Log.d(TAG, "Sony autofocus request coalesced; one is already active")
            return
        }
        // Creators' App uses RemoteTouchOperation on the existing PTP session;
        // no SSH teardown or S1 half-press is required for focus.
        thread(name = "SonyProductionAF") {
            val ok = try {
                commandLock.withLock {
                    try {
                        camera.driveTouchFocus(normalizedX, normalizedY)
                    } catch (e: Exception) {
                        Log.w(TAG, "Live Sony autofocus failed: ${e.message}")
                        false
                    }
                }
            } finally {
                autofocusInFlight.set(false)
            }
            mainHandler.post { onResult(ok) }
        }
    }

    fun driveZoom(tele: Boolean, durationMs: Long, onResult: (Boolean) -> Unit = {}) {
        runFreshControl("SonyProductionZoom", onResult) {
            it.driveZoom(tele, durationMs.coerceIn(80L, 1_500L))
        }
    }

    fun setZoomRatio(ratio: Float, onResult: (Boolean) -> Unit = {}) {
        runFreshControl("SonyProductionZoomScale", onResult) { it.setZoomRatio(ratio) }
    }

    fun setExposureCompensationEv(ev: Float, onResult: (Boolean) -> Unit = {}) {
        // Sony PTP 0x5010 uses signed thousandths of an EV, but this body
        // advertises 1/3-stop candidates as 0, ±300, ±700, ±1000... .
        val thirds = (ev * 3f).roundToInt()
        val milliEv = ((thirds * 1_000f / 3f) / 100f).roundToInt() * 100
        runFreshControl("SonyProductionExposure", onResult) {
            it.setExposureCompensation(milliEv)
        }
    }

    fun setIso(iso: Int?, onResult: (Boolean) -> Unit = {}) {
        val wireValue = iso ?: SONY_ISO_AUTO
        runFreshControl("SonyProductionIso", onResult) { it.setIso(wireValue) }
    }

    fun setWhiteBalance(value: Int, onResult: (Boolean) -> Unit = {}) {
        runFreshControl("SonyProductionWhiteBalance", onResult) { it.setWhiteBalance(value) }
    }

    fun setExposureMode(value: Int, onResult: (Boolean) -> Unit = {}) {
        runFreshControl("SonyProductionExposureMode", onResult) { it.setExposureMode(value) }
    }

    fun setShutterSpeed(
        numerator: Int,
        denominator: Int,
        onResult: (Boolean) -> Unit = {}
    ) {
        runFreshControl("SonyProductionShutter", onResult) {
            it.setShutterSpeed(numerator, denominator)
        }
    }

    fun setFNumber(fNumberTimes100: Int, onResult: (Boolean) -> Unit = {}) {
        runFreshControl("SonyProductionAperture", onResult) {
            it.setFNumber(fNumberTimes100)
        }
    }

    fun setFocusMode(value: Int, onResult: (Boolean) -> Unit = {}) {
        runFreshControl("SonyProductionFocusMode", onResult) { it.setFocusMode(value) }
    }

    fun setFocusArea(value: Int, onResult: (Boolean) -> Unit = {}) {
        runFreshControl("SonyProductionFocusArea", onResult) { it.setFocusArea(value) }
    }

    fun setExposureMeteringMode(value: Int, onResult: (Boolean) -> Unit = {}) {
        runFreshControl("SonyProductionMetering", onResult) {
            it.setExposureMeteringMode(value)
        }
    }

    fun applyQualitySettings(
        settings: SonyQualitySettings,
        onResult: (Boolean) -> Unit = {}
    ) {
        desiredQualitySettings = settings
        captureQualityVerified = false
        runFreshControl("SonyProductionQuality", onResult) {
            it.applyQualitySettings(settings)
        }
    }

    /**
     * Run controls on the existing persistent PTP command connection. The
     * controller briefly releases/reopens HTTP only for operations this body
     * cannot execute concurrently with Live View. Replacing the whole session
     * for each adjustment caused multi-second preview outages and reconnect
     * cascades.
     */
    private fun runFreshControl(
        threadName: String,
        onResult: (Boolean) -> Unit,
        action: (SonyPtpIpController) -> Boolean
    ) {
        val camera: SonyPtpIpController
        val expectedGeneration: Long
        synchronized(stateLock) {
            if (!isAvailable || captureMode || controlTransition || connectInFlight ||
                !controlInFlight.compareAndSet(false, true)
            ) {
                mainHandler.post { onResult(false) }
                return
            }
            camera = controller ?: run {
                controlInFlight.set(false)
                mainHandler.post { onResult(false) }
                return
            }
            expectedGeneration = generation
        }

        thread(name = threadName) {
            val ok = try {
                commandLock.withLock {
                    if (running && generation == expectedGeneration &&
                        controller === camera && camera.isConnected
                    ) {
                        try {
                            action(camera)
                        } catch (e: Exception) {
                            Log.w(TAG, "$threadName failed: ${e.message}")
                            false
                        }
                    } else false
                }
            } finally {
                controlInFlight.set(false)
            }
            mainHandler.post { onResult(ok) }
        }
    }

    companion object {
        private const val TAG = "SonyProduction"
        private const val FRAME_INTERVAL_MS = 33L
        private const val MAX_CONSECUTIVE_FRAME_FAILURES = 8
        private const val CAPTURE_REOPEN_SETTLE_MS = 300L
        private const val CAPTURE_BURST_IDLE_MS = 750L
        private const val CAPTURE_BEST_OF_FRAMES = 5
        private const val POWER_CONFIGURATION_HINT_ATTEMPT = 4
        private const val SONY_ISO_AUTO = 0x00FF_FFFF
    }
}
