package com.aradhana.capturecam

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.Process
import android.os.SystemClock
import android.util.Log
import kotlin.concurrent.thread
import kotlin.math.min
import java.util.concurrent.Executors
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
    context: Context,
    private val onFrame: (android.graphics.Bitmap) -> Unit,
    private val onAvailabilityChanged: (Boolean, String) -> Unit
) {
    private val appContext = context.applicationContext
    private val wifiManager =
        appContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val liveViewWifiLock: WifiManager.WifiLock = wifiManager.createWifiLock(
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            WifiManager.WIFI_MODE_FULL_LOW_LATENCY
        } else {
            @Suppress("DEPRECATION")
            WifiManager.WIFI_MODE_FULL_HIGH_PERF
        },
        "CaptureCam:SonyLiveView"
    ).apply { setReferenceCounted(false) }
    private val mainHandler = Handler(Looper.getMainLooper())
    private val stateLock = Any()
    // Optional per-frame instantaneous-fps listener for the live UI graph
    // (2026-08-26). Fires on the live-loop background thread, same as
    // [onFrame] -- callers must post to the main thread themselves.
    @Volatile var onFrameTiming: ((Float) -> Unit)? = null
    // Fires on a background thread (2026-08-28) whenever rediscovery finds
    // the camera at a new address, so the caller can persist it (see
    // MainActivity's "sony_camera_ip" pref) for next launch. Purely
    // informational -- this instance already switches to the new IP itself.
    @Volatile var onCameraIpChanged: ((String) -> Unit)? = null
    @Volatile private var discoveryInFlight = false

    @Volatile private var running = false
    @Volatile private var liveRunning = false
    @Volatile private var frameReady = false
    @Volatile private var connectInFlight = false
    private val commandLock = ReentrantLock()
    private val autofocusInFlight = AtomicBoolean(false)
    // Sony owns one transactional PTP command lane. Queue commands on one
    // worker instead of dropping whichever request happens to arrive while
    // another is active. Callers already conflate high-rate zoom/exposure
    // intent, so this queue contains only the newest meaningful operations.
    private val controlExecutor = Executors.newSingleThreadExecutor { runnable ->
        Thread({
            Process.setThreadPriority(Process.THREAD_PRIORITY_DEFAULT)
            runnable.run()
        }, "SonyProductionControl").apply { isDaemon = true }
    }
    @Volatile private var controller: SonyPtpIpController? = null
    @Volatile private var captureController: SonyPtpIpController? = null
    @Volatile private var captureMode = false
    @Volatile private var captureConnectInFlight = false
    @Volatile private var desiredQualitySettings: SonyQualitySettings? = null
    @Volatile private var captureQualityVerified = false
    private val captureQualityPreparationInFlight = AtomicBoolean(false)
    @Volatile private var controlTransition = false
    @Volatile private var latestFocusIndication: Int? = null
    @Volatile private var latestFocusIndicationAtNanos = 0L
    @Volatile private var latestLiveViewJpeg: ByteArray? = null
    private var finishCaptureRunnable: Runnable? = null
    private var generation = 0L
    private var liveLoopEpoch = 0L
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

    /** Immutable camera-produced JPEG for lightweight tag evidence. Avoids
     * recompressing a pooled Bitmap on MainActivity's UI thread. */
    fun currentLiveViewJpeg(): ByteArray? = latestLiveViewJpeg?.copyOf()

    data class FocusSnapshot(val indication: Int, val receivedAtNanos: Long)

    fun currentFocusSnapshot(): FocusSnapshot? {
        val indication = latestFocusIndication ?: return null
        val receivedAt = latestFocusIndicationAtNanos
        return if (receivedAt > 0L) FocusSnapshot(indication, receivedAt) else null
    }

    val isCaptureBusy: Boolean
        get() = captureMode || captureConnectInFlight

    val isCaptureQualityVerified: Boolean
        get() = captureQualityVerified

    /** Read-only diagnostic for card visibility in the active Remote session. */
    fun probeCardObjects(onResult: (SonyPtpIpController.CardObjectProbe?) -> Unit) {
        val camera = controller
        if (!isAvailable || camera == null || !camera.isConnected || captureMode || controlTransition) {
            mainHandler.post { onResult(null) }
            return
        }
        thread(name = "SonyCardObjectProbe") {
            val result = commandLock.withLock {
                try {
                    camera.probeCardObjects()
                } catch (e: Exception) {
                    Log.e(TAG, "Sony card-object probe failed", e)
                    null
                }
            }
            mainHandler.post { onResult(result) }
        }
    }

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
        try {
            if (!liveViewWifiLock.isHeld) liveViewWifiLock.acquire()
            Log.i(TAG, "Sony low-latency WiFi lock acquired=${liveViewWifiLock.isHeld}")
        } catch (e: Exception) {
            Log.w(TAG, "Sony low-latency WiFi lock unavailable: ${e.message}")
        }
        connectOnce(generation)
    }

    /** Supplies the complete profile before connection. It is applied after
     * PTP authentication but before the Live View pump starts, so startup
     * never shows a stream and then tears it down again for configuration. */
    fun setStartupQualitySettings(settings: SonyQualitySettings) {
        desiredQualitySettings = settings
        captureQualityVerified = false
    }

    fun stop() {
        val old: SonyPtpIpController?
        synchronized(stateLock) {
            running = false
            liveRunning = false
            frameReady = false
            latestLiveViewJpeg = null
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
        try {
            if (liveViewWifiLock.isHeld) liveViewWifiLock.release()
        } catch (e: Exception) {
            Log.w(TAG, "Sony low-latency WiFi lock release failed: ${e.message}")
        }
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
            val desired = desiredQualitySettings
            captureQualityVerified = if (desired == null) {
                true
            } else {
                try {
                    candidate.applyQualitySettings(desired).also { applied ->
                        Log.i(TAG, "Sony pre-stream quality profile applied=$applied settings=$desired")
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Sony pre-stream quality profile failed: ${e.message}", e)
                    false
                }
            }
            synchronized(stateLock) {
                controller?.disconnect()
                controller = candidate
            }
            startLiveLoop(candidate, expectedGeneration)
        }
    }

    private fun startLiveLoop(camera: SonyPtpIpController, expectedGeneration: Long) {
        val expectedLiveLoopEpoch = synchronized(stateLock) {
            liveLoopEpoch += 1L
            liveLoopEpoch
        }
        camera.setLiveViewStreaming(true)
        liveRunning = true
        frameReady = false
        thread(name = "SonyProductionLiveView") {
            Process.setThreadPriority(Process.THREAD_PRIORITY_DISPLAY)
            val loopStartedAt = SystemClock.elapsedRealtime()
            // BitmapFactory otherwise allocates ~1.1MB native ARGB storage for
            // every 640x424 frame (~27MB/s at 25fps). That grew RSS past
            // 500MB and caused periodic GC/catch-up bursts visible as severe
            // preview stutter. Three mutable buffers protect the displayed
            // and detector frames while eliminating steady-state allocation.
            val decodePool = arrayOfNulls<Bitmap>(3)
            var decodeSlot = 0
            val decodeOptions = BitmapFactory.Options().apply {
                inMutable = true
                inPreferredConfig = Bitmap.Config.ARGB_8888
            }
            var failures = 0
            var firstFrame = true
            var lastLoggedFocusIndication: Int? = null
            var cadenceWindowStartedAt = SystemClock.elapsedRealtime()
            var cadenceFrames = 0
            var lastFrameAtElapsed = 0L
            while (running && liveRunning && generation == expectedGeneration &&
                liveLoopEpoch == expectedLiveLoopEpoch && controller === camera && camera.isConnected
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
                    latestFocusIndicationAtNanos = sample.receivedAtNanos
                    if (focus != lastLoggedFocusIndication) {
                        Log.i(TAG, "Sony AF indication=$focus frame=${sample.sequence}")
                        lastLoggedFocusIndication = focus
                    }
                }
                val bitmap = sample?.let {
                    latestLiveViewJpeg = it.jpeg
                    decodeOptions.inBitmap = decodePool[decodeSlot]
                    val decoded = try {
                        BitmapFactory.decodeByteArray(it.jpeg, 0, it.jpeg.size, decodeOptions)
                    } catch (_: IllegalArgumentException) {
                        // Stream dimensions/config can change after a camera
                        // mode transition. Allocate this slot once at the new
                        // shape, then resume reuse on subsequent frames.
                        decodeOptions.inBitmap = null
                        BitmapFactory.decodeByteArray(it.jpeg, 0, it.jpeg.size, decodeOptions)
                    }
                    if (decoded != null) {
                        decodePool[decodeSlot] = decoded
                        decodeSlot = (decodeSlot + 1) % decodePool.size
                        // Pre-warm the other two pool slots off the FIRST
                        // successful decode (2026-08-26 fix): before this,
                        // each of the first 3 frames hit the slow fresh-
                        // allocation path (inBitmap=null) one at a time as
                        // the pool cycled through its empty slots -- visible
                        // live as stutter on exactly the first few frames
                        // after every reconnect. Frame dimensions aren't
                        // known until this first real decode, so slots can't
                        // be pre-allocated any earlier than this; allocating
                        // the remaining two here means only frame 1 pays the
                        // slow path instead of frames 1-3.
                        for (i in decodePool.indices) {
                            if (decodePool[i] == null) {
                                decodePool[i] = Bitmap.createBitmap(
                                    decoded.width, decoded.height, Bitmap.Config.ARGB_8888
                                )
                            }
                        }
                    }
                    decoded
                }
                if (bitmap == null) {
                    if (firstFrame &&
                        SystemClock.elapsedRealtime() - loopStartedAt < LIVE_RESUME_FIRST_FRAME_GRACE_MS
                    ) {
                        try { Thread.sleep(50L) } catch (_: InterruptedException) { break }
                        continue
                    }
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
                // Per-frame instantaneous fps, for the live UI graph -- the
                // existing renderedFps log line only updates every 5s, too
                // coarse to visually diagnose a stutter confined to a few
                // individual frames. Optional/no-op unless the UI has wired
                // a listener (see MainActivity's fpsGraph wiring).
                val nowElapsed = SystemClock.elapsedRealtime()
                if (lastFrameAtElapsed != 0L) {
                    val deltaMs = nowElapsed - lastFrameAtElapsed
                    if (deltaMs > 0) {
                        val instantFps = 1000f / deltaMs
                        try {
                            onFrameTiming?.invoke(instantFps)
                        } catch (e: Exception) {
                            Log.e(TAG, "Sony production frame-timing listener failed", e)
                        }
                    }
                }
                lastFrameAtElapsed = nowElapsed
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
            val stillOwnsProductionSession = synchronized(stateLock) {
                if (liveLoopEpoch == expectedLiveLoopEpoch && controller === camera) {
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
            if (stillOwnsProductionSession) camera.disconnect()
            if (stillOwnsProductionSession && running && generation == expectedGeneration &&
                !captureMode && !controlTransition
            ) {
                val sessionAgeMs = liveSessionStartedAtMs.takeIf { it > 0L }
                    ?.let { SystemClock.elapsedRealtime() - it }
                Log.w(
                    TAG,
                    "Sony Live View lost; sessionAge=${sessionAgeMs?.let(::formatDuration) ?: "unknown"}"
                )
                // The pump exits after eight HTTP 503s or after a replacement
                // stream also fails. Local SSH state can still say connected
                // while Sony's producer is wedged, so replace the whole
                // session. Preserve the last good frame during the ~1.4s
                // reconnect instead of flashing the CameraX fallback.
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
            // DHCP-assigned IPs for both devices are NOT stable across a
            // Wi-Fi reconnect (confirmed live, 2026-08-28: camera moved
            // 192.168.0.14 -> .20 mid-session with zero warning beyond
            // "connection refused"). One grace failure first (reconnectAttempt
            // == 2 here, i.e. the second consecutive failure) in case this is
            // just a transient blip, then sweep the subnet in parallel with
            // the normal backoff retry -- if it finds the camera at a new
            // address before the next scheduled retry fires, switch to it
            // and retry immediately instead of waiting out the backoff.
            if (reconnectAttempt == 2 && !discoveryInFlight) {
                discoveryInFlight = true
                thread(name = "SonyCameraRediscovery", isDaemon = true) {
                    try {
                        val found = SonyCameraDiscovery.discoverCameraIp(appContext, sshUser, sshPassword, cameraIp)
                        if (found != null && found != cameraIp && running && generation == expectedGeneration) {
                            Log.i(TAG, "Sony camera rediscovered at $found (was $cameraIp)")
                            cameraIp = found
                            onCameraIpChanged?.invoke(found)
                            synchronized(stateLock) {
                                reconnectRunnable?.let(mainHandler::removeCallbacks)
                                reconnectRunnable = null
                                reconnectAttempt = 0
                            }
                            connectOnce(expectedGeneration)
                        }
                    } catch (e: Exception) {
                        Log.w(TAG, "Sony camera rediscovery failed: ${e.message}", e)
                    } finally {
                        discoveryInFlight = false
                    }
                }
            }
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

    /**
     * Takes one verified original-resolution Sony still.
     *
     * Best-of-five stays diagnostic-only. The ZV-E10 II exposes one volatile
     * host object at a time and does not support RemoteTransfer mode; pulling
     * five RAW+JPEG originals synchronously held production for ~20 seconds.
     */
    fun captureStill(onResult: (ByteArray?) -> Unit) =
        captureStill(onShutterAccepted = {}, onResult = onResult)

    fun captureStill(
        onShutterAccepted: () -> Unit,
        onResult: (ByteArray?) -> Unit
    ) {
        finishCaptureRunnable?.let(mainHandler::removeCallbacks)
        finishCaptureRunnable = null

        captureController?.takeIf { it.isConnected }?.let { camera ->
            captureOnSession(camera, onShutterAccepted, onResult)
            return
        }

        val liveCamera: SonyPtpIpController
        synchronized(stateLock) {
            if (!isAvailable || captureMode || captureConnectInFlight) {
                mainHandler.post { onResult(null) }
                return
            }
            liveCamera = controller ?: run {
                mainHandler.post { onResult(null) }
                return
            }
            captureMode = true
            captureController = liveCamera
        }

        // Keep the dedicated HTTP Live View pump draining while the PTP
        // control channel captures/downloads the original. Closing it here
        // made Sony's internal HTTP producer wedge after a still: measured
        // 20-25s before Live View returned, during which every side-angle
        // capture was rejected as unavailable. The pump owns a separate SSH
        // session/channel and latest-wins buffer, so leaving it alive creates
        // no stale-frame queue and mirrors Creators' App's persistent view.
        // The HTTP pump and render loop remain live during the PTP still
        // transfer. This lets the operator position the next angle while the
        // 17-18MB original downloads on Sony's one serialized command lane.
        onAvailabilityChanged(true, "Sony transferring original in background…")
        captureOnSession(liveCamera, onShutterAccepted, onResult)
    }

    private fun captureOnSession(
        camera: SonyPtpIpController,
        onShutterAccepted: () -> Unit,
        onResult: (ByteArray?) -> Unit
    ) {
        thread(name = "SonyProductionCapture") {
            val bytes = commandLock.withLock {
                try {
                    // Quality is prepared before AF starts. Applying a
                    // profile here made shutter wait seconds after focus and
                    // could expose a stale/soft pose. Fail closed instead.
                    val qualityOk = captureQualityVerified
                    if (!qualityOk) {
                        Log.w(TAG, "Sony capture blocked: quality profile was not ready before final focus")
                        null
                    } else {
                        if (camera.triggerShutter(onShotReady = {
                                mainHandler.post(onShutterAccepted)
                            })) {
                            camera.lastCapturedImage.also {
                                Log.i(TAG, "Sony production single original bytes=${it?.size}")
                            }
                        } else null
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
        useSmallProxies: Boolean = false,
        onResult: (SonyPtpIpController.BurstTestResult?) -> Unit
    ) {
        finishCaptureRunnable?.let(mainHandler::removeCallbacks)
        finishCaptureRunnable = null

        captureController?.takeIf { it.isConnected }?.let { camera ->
            burstOnSession(camera, frameCount, useSmallProxies, onResult)
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
            burstOnSession(camera, frameCount, useSmallProxies, onResult)
        }
    }

    private fun burstOnSession(
        camera: SonyPtpIpController,
        frameCount: Int,
        useSmallProxies: Boolean,
        onResult: (SonyPtpIpController.BurstTestResult?) -> Unit
    ) {
        thread(name = "SonyProductionBurst") {
            val result = commandLock.withLock {
                try {
                    val desired = desiredQualitySettings
                    // Proxy timing diagnostics deliberately preserve the
                    // already-running camera profile. Reapplying the entire
                    // quality hardwall here can reject an unrelated focus-
                    // area readback before the transfer test even starts.
                    val qualityOk = useSmallProxies || captureQualityVerified ||
                        (desired == null || camera.applyQualitySettings(desired)).also {
                            captureQualityVerified = it
                        }
                    if (!qualityOk) {
                        null
                    } else if (useSmallProxies) {
                        camera.triggerProxyBurstTest(frameCount)
                    } else {
                        camera.triggerBurstTest(frameCount)
                    }
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
        var resumeCamera: SonyPtpIpController? = null
        var retainedLiveCamera = false
        var reconnect = false
        synchronized(stateLock) {
            finishCaptureRunnable?.let(mainHandler::removeCallbacks)
            finishCaptureRunnable = null
            val camera = captureController
            captureController = null
            captureConnectInFlight = false
            captureMode = false
            if (running && generation == expectedGeneration && camera?.isConnected == true &&
                controller === camera && liveRunning
            ) {
                retainedLiveCamera = true
            } else if (running && generation == expectedGeneration && camera?.isConnected == true) {
                controller = camera
                resumeCamera = camera
            } else {
                camera?.disconnect()
                captureQualityVerified = false
                reconnect = running && generation == expectedGeneration
            }
        }
        if (retainedLiveCamera) onAvailabilityChanged(true, "Sony live")
        resumeCamera?.let { startLiveLoop(it, expectedGeneration) }
        if (reconnect) connectOnce(expectedGeneration)
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

    /**
     * One indivisible final-still focus transaction.  AF-S selection and the
     * RemoteTouchOperation must hold the same command lock: queueing them as
     * two independent controls allowed a pending AF-C restore to run between
     * them, so the camera acknowledged the touch but continued hunting.
     */
    fun autofocusForStill(
        normalizedX: Float,
        normalizedY: Float,
        onResult: (Boolean) -> Unit = {}
    ) {
        runFreshControl("SonyProductionAFSFocus", onResult) { camera ->
            // The tablet starts Sony in TAG/Wide. Wide remains valid for
            // label acquisition but lets AF choose the high-contrast acrylic
            // rail during jewellery capture. Set Tracking Spot L immediately
            // before the target touch, on this same serialized transaction.
            camera.setFocusArea(FOCUS_AREA_TRACKING_SPOT_L) &&
                camera.setFocusMode(SonyPtpIpController.AFMODE_AFS) &&
                camera.driveTouchFocus(normalizedX, normalizedY)
        }
    }

    fun driveZoom(tele: Boolean, durationMs: Long, onResult: (Boolean) -> Unit = {}) {
        runFreshControl("SonyProductionZoom", onResult) {
            it.driveZoom(tele, durationMs.coerceIn(80L, 1_800L))
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
        if (desiredQualitySettings == settings && captureQualityVerified) {
            mainHandler.post { onResult(true) }
            return
        }
        desiredQualitySettings = settings
        captureQualityVerified = false
        runFreshControl("SonyProductionQuality", { ok ->
            captureQualityVerified = ok
            onResult(ok)
        }) {
            it.applyQualitySettings(settings)
        }
    }

    /** Prepare the full operator-selected profile before a final AF request.
     * Repeated UI ticks coalesce into one command-lane transaction. */
    fun prepareCaptureQuality(onResult: (Boolean) -> Unit = {}) {
        if (captureQualityVerified) {
            mainHandler.post { onResult(true) }
            return
        }
        if (!captureQualityPreparationInFlight.compareAndSet(false, true)) {
            mainHandler.post { onResult(false) }
            return
        }
        val desired = desiredQualitySettings
        if (desired == null) {
            captureQualityVerified = true
            captureQualityPreparationInFlight.set(false)
            mainHandler.post { onResult(true) }
            return
        }
        runFreshControl("SonyProductionPrepareQuality", { ok ->
            captureQualityVerified = ok
            captureQualityPreparationInFlight.set(false)
            onResult(ok)
        }) { it.applyQualitySettings(desired) }
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
            if (!isAvailable || captureMode || controlTransition || connectInFlight) {
                mainHandler.post { onResult(false) }
                return
            }
            camera = controller ?: run {
                mainHandler.post { onResult(false) }
                return
            }
            expectedGeneration = generation
        }

        controlExecutor.execute {
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
            } catch (e: Exception) {
                Log.w(TAG, "$threadName worker failed: ${e.message}")
                false
            }
            mainHandler.post { onResult(ok) }
        }
    }

    companion object {
        private const val TAG = "SonyProduction"
        private const val FRAME_INTERVAL_MS = 33L
        private const val MAX_CONSECUTIVE_FRAME_FAILURES = 8
        private const val LIVE_RESUME_FIRST_FRAME_GRACE_MS = 12_000L
        private const val CAPTURE_REOPEN_SETTLE_MS = 300L
        private const val CAPTURE_BURST_IDLE_MS = 100L
        private const val POWER_CONFIGURATION_HINT_ATTEMPT = 4
        private const val SONY_ISO_AUTO = 0x00FF_FFFF
        private const val FOCUS_AREA_TRACKING_SPOT_L = 518
    }
}
