package com.aradhana.capturecam

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import kotlin.concurrent.thread

/**
 * RSC 2 BLE hardware-validation harness -- deliberately NOT part of the
 * production capture pipeline. DJI publishes no developer SDK for the
 * RSC 2 (R SDK covers RS 2/RS 3 Pro/RS 4/RS 4 Pro/RS 5, not this model),
 * so controlling it means working against a reverse-engineered protocol.
 * Before any category-calibration/motion-controller architecture gets
 * built on top of that assumption, this screen exists to answer the
 * concrete question: can THIS app, from THIS phone, discover the gimbal
 * over BLE, see its GATT services/characteristics, and successfully write
 * to one of them? Nothing here assumes what those characteristics or byte
 * formats are -- that's the whole point of a discovery tool instead of a
 * hardcoded driver.
 *
 * Milestone this maps to (RSC2 BLE PROOF):
 *   1. Discover RSC 2       -> Scan button, device list
 *   2. Connect               -> tap a discovered device
 *   3. Identify GATT surface -> service/characteristic list after connect
 *   4-9. Send low-speed pan commands, confirm physical movement, stop,
 *        repeat -- once real command bytes are known (from a BLE sniff of
 *        DJI's own Ronin app, or trial/error), use the hex-bytes field
 *        against a selected characteristic. This screen doesn't know or
 *        guess those bytes; a human watching the gimbal move is the only
 *        real confirmation step 5/8 have, which is why this is a manual
 *        tool, not an automated test.
 */
class BleDiagnosticsActivity : AppCompatActivity() {

    private lateinit var statusText: TextView
    private lateinit var logText: TextView
    private lateinit var logScroll: ScrollView
    private lateinit var deviceListContainer: LinearLayout
    private lateinit var characteristicListContainer: LinearLayout
    private lateinit var hexBytesInput: EditText
    private lateinit var axis1Input: EditText
    private lateinit var axis2Input: EditText
    private lateinit var axis3Input: EditText

    private val handler = Handler(Looper.getMainLooper())
    private val bluetoothAdapter by lazy {
        (getSystemService(BLUETOOTH_SERVICE) as BluetoothManager).adapter
    }
    private var gatt: BluetoothGatt? = null
    private var selectedCharacteristic: BluetoothGattCharacteristic? = null
    private val seenAddresses = mutableSetOf<String>()
    private var scanning = false
    // The repeat-send loop schedules up to 15 sends over ~3s via
    // postDelayed -- nothing was cancelling that when the user then hit
    // STOP mid-loop, so leftover scheduled sends kept re-deflecting the
    // gimbal right after the neutral frame landed ("neutral doesn't work").
    // Tracking the active loop lets every stop/new-send path cancel it.
    private var activeRepeatRunnable: Runnable? = null
    // DUML sequence counter -- increments per frame sent this session. The
    // real device didn't appear to require strict continuity from a fresh
    // start, but incrementing avoids relying on that being true.
    private var duMLSeq = 1

    private val requestPermissions = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        if (results.values.all { it }) {
            if (pendingSonyGimbalConnect) {
                pendingSonyGimbalConnect = false
                connectSonyTrackingGimbal()
            } else {
                startScan()
            }
        } else {
            pendingSonyGimbalConnect = false
            log("Permissions denied -- cannot connect to the gimbal.")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContentView(R.layout.activity_ble_diagnostics)

        statusText = findViewById(R.id.bleStatusText)
        // Long-press to toggle NothingCameraBridge as MainActivity's jewel
        // capture source, instead of this app's own CameraX pipeline --
        // deliberately hidden here (debug-only screen), not on the live
        // capture UI, while this path is still being validated against
        // real capture volume. Defaults to false (existing CameraX
        // behavior) on every fresh app install; persists across app
        // restarts via SharedPreferences so it doesn't need re-enabling
        // every launch once a device is confirmed working with it.
        statusText.setOnLongClickListener {
            val prefs = getSharedPreferences("capturecam_debug", MODE_PRIVATE)
            val next = !prefs.getBoolean("use_nothing_camera", false)
            prefs.edit().putBoolean("use_nothing_camera", next).apply()
            Toast.makeText(
                this,
                if (next) "Nothing Camera capture: ON (needs Settings > Accessibility enabled)"
                else "Nothing Camera capture: OFF (using CaptureCam's own camera)",
                Toast.LENGTH_LONG
            ).show()
            true
        }
        logText = findViewById(R.id.logText)
        logScroll = findViewById(R.id.logScroll)
        deviceListContainer = findViewById(R.id.deviceListContainer)
        characteristicListContainer = findViewById(R.id.characteristicListContainer)
        hexBytesInput = findViewById(R.id.hexBytesInput)
        axis1Input = findViewById(R.id.axis1Input)
        axis2Input = findViewById(R.id.axis2Input)
        axis3Input = findViewById(R.id.axis3Input)

        findViewById<Button>(R.id.scanButton).setOnClickListener { requestPermissionsThenScan() }
        findViewById<Button>(R.id.disconnectButton).setOnClickListener { disconnect() }
        findViewById<Button>(R.id.sendBytesButton).setOnClickListener { sendHexToSelected() }
        findViewById<Button>(R.id.repeatSendButton).setOnClickListener { sendHexRepeatedly() }
        findViewById<Button>(R.id.sendCustomOnceButton).setOnClickListener { sendCustomJoystickFrame(repeat = false) }
        findViewById<Button>(R.id.sendCustomRepeatButton).setOnClickListener { sendCustomJoystickFrame(repeat = true) }
        findViewById<Button>(R.id.sendNeutralButton).setOnClickListener { sendNeutral() }

        setupSonyTestPanel()

        log("Ready. Turn on the RSC 2, put it in Bluetooth pairing mode (per its manual), then tap Scan.")
    }

    // --- Sony ZV-E10 II PTP-IP test panel -----------------------------
    // Same "manual proof-of-concept, human confirms real hardware motion"
    // philosophy as the RSC 2 section above -- SonyPtpIpController is a
    // first-draft reverse-engineered implementation (see its own doc
    // comment for sourcing), unverified against a real ZV-E10 II until run
    // from here. Set the camera to remote-control/PC-Remote mode first --
    // it displays its own SSID+password on its screen.

    private val sonyWifi by lazy { SonyWifiConnectionManager(this) }
    private var sonyController: SonyPtpIpController? = null
    private lateinit var sonyStatusText: TextView
    private lateinit var sonyLiveViewContainer: View
    private lateinit var sonyLiveViewImage: ImageView
    private lateinit var sonyGoldOverlay: BoundsOverlayView
    private lateinit var sonyTrackingStatusText: TextView
    private lateinit var sonyLiveStreamButton: Button
    private lateinit var sonyAutoTrackButton: Button
    private val sonyTrackingGimbal = RSC2Controller()
    private val sonyGoldServo = SonyGoldServoController()
    private val sonyGoldTargetDetector = SonyGoldTargetDetector()
    @Volatile private var sonyLiveRunning = false
    @Volatile private var sonyAutoTracking = false
    private var sonyLiveThread: Thread? = null
    @Volatile private var sonyLiveGeneration = 0L
    private var pendingSonyGimbalConnect = false
    @Volatile private var sonyGimbalConnecting = false
    private var sonyFrameCount = 0L
    private var sonyAnalysisFrameId = 0L
    private var sonyFrameWindowStarted = 0L
    private var sonyLastFrameLogAt = 0L
    private data class SonyUiFrame(
        val generation: Long,
        val bitmap: Bitmap,
        val goldPoints: List<MaterialDetector.Point>,
        val target: SonyGoldTargetDetector.Target?,
        val decision: SonyGoldServoController.Decision,
        val candidateCount: Int,
        val fps: Float,
        val networkMs: Long,
        val decodeMs: Long,
        val analysisMs: Long
    )
    private val sonyLatestUiFrame = AtomicReference<SonyUiFrame?>(null)
    private val sonyUiUpdatePending = AtomicBoolean(false)
    private val sonyUiDrainRunnable = object : Runnable {
        override fun run() {
            val frame = sonyLatestUiFrame.getAndSet(null)
            if (frame != null && sonyLiveRunning && frame.generation == sonyLiveGeneration) {
                renderSonyUiFrame(frame)
            }
            sonyUiUpdatePending.set(false)
            // A newer frame may have arrived between getAndSet() and the
            // pending reset. Schedule exactly one more render; intermediate
            // frames remain intentionally dropped so preview never queues.
            if (sonyLatestUiFrame.get() != null &&
                sonyUiUpdatePending.compareAndSet(false, true)
            ) {
                handler.post(this)
            }
        }
    }
    @Volatile private var sonyLiveDesired = false
    @Volatile private var sonyRecoveryEnabled = true
    @Volatile private var sonyConnectInFlight = false
    private var sonyConnectionGeneration = 0L
    private var sonyReconnectAttempt = 0
    private var sonyReconnectRunnable: Runnable? = null
    private var sonyConnectionSpec: SonyConnectionSpec? = null

    private data class SonyConnectionSpec(
        val ip: String,
        val sshUser: String,
        val sshPassword: String
    )

    private fun setupSonyTestPanel() {
        sonyStatusText = findViewById(R.id.sonyStatusText)
        sonyLiveViewContainer = findViewById(R.id.sonyLiveViewContainer)
        sonyLiveViewImage = findViewById(R.id.sonyLiveViewImage)
        sonyGoldOverlay = findViewById(R.id.sonyGoldOverlay)
        sonyTrackingStatusText = findViewById(R.id.sonyTrackingStatusText)
        sonyLiveStreamButton = findViewById(R.id.sonyLiveStreamButton)
        sonyAutoTrackButton = findViewById(R.id.sonyAutoTrackButton)
        val ipInput = findViewById<EditText>(R.id.sonyIpInput)
        val sshUserInput = findViewById<EditText>(R.id.sonySshUserInput)
        val sshPasswordInput = findViewById<EditText>(R.id.sonySshPasswordInput)

        sonyTrackingGimbal.onUnexpectedDisconnect = {
            handler.post {
                log("Sony tracking: gimbal disconnected; reconnecting…")
                if (sonyAutoTracking) connectSonyTrackingGimbal()
            }
        }

        findViewById<Button>(R.id.sonyConnectButton).setOnClickListener {
            val ip = ipInput.text.toString().trim()
            val sshUser = sshUserInput.text.toString().trim()
            val sshPassword = sshPasswordInput.text.toString()
            if (ip.isEmpty() || sshUser.isEmpty()) {
                log("Sony: enter the camera IP and the User/Password from its Access Authen. Info screen")
                return@setOnClickListener
            }
            // A manual connection refresh must not force a failing Live View
            // request into the new command session. Preserve an already
            // requested preview, but keep a connection-only session stable
            // until the operator explicitly starts the stream.
            stopSonyLiveView(userRequested = false)
            sonyRecoveryEnabled = true
            sonyConnectionSpec = SonyConnectionSpec(ip, sshUser, sshPassword)
            sonyConnectionGeneration += 1L
            sonyReconnectAttempt = 0
            cancelSonyReconnect()
            connectSonyOnce(sonyConnectionGeneration)
        }

        findViewById<Button>(R.id.sonyShutterButton).setOnClickListener {
            val controller = sonyController
            if (controller == null) { log("Sony: not connected"); return@setOnClickListener }
            log("Sony: triggering shutter...")
            Thread {
                val ok = controller.triggerShutter()
                handler.post { log("Sony: shutter trigger ${if (ok) "sent" else "FAILED"}") }
            }.start()
        }

        findViewById<Button>(R.id.sonyZoomTeleButton).setOnClickListener {
            val controller = sonyController
            if (controller == null) { log("Sony: not connected"); return@setOnClickListener }
            log("Sony: zooming tele for 600ms...")
            Thread { controller.driveZoom(tele = true, durationMs = 600L) }.start()
        }

        findViewById<Button>(R.id.sonyZoomWideButton).setOnClickListener {
            val controller = sonyController
            if (controller == null) { log("Sony: not connected"); return@setOnClickListener }
            log("Sony: zooming wide for 600ms...")
            Thread { controller.driveZoom(tele = false, durationMs = 600L) }.start()
        }

        findViewById<Button>(R.id.sonyLiveViewButton).setOnClickListener {
            val controller = sonyController
            if (controller == null) { log("Sony: not connected"); return@setOnClickListener }
            log("Sony: probing one PTP virtual-object live-view frame...")
            Thread {
                val frame = controller.fetchLiveViewFrameRaw()
                val bitmap = frame?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
                handler.post {
                    if (frame != null && bitmap != null) {
                        sonyLiveViewContainer.visibility = View.VISIBLE
                        sonyLiveViewImage.setImageBitmap(bitmap)
                        sonyTrackingStatusText.text = "Sony Live View ${bitmap.width}×${bitmap.height} — ${frame.size} bytes"
                        log("Sony: decoded PTP Live View JPEG ${bitmap.width}x${bitmap.height}, ${frame.size} bytes")
                        log("Sony: ${controller.lastLiveViewDiagnostic}")
                    } else {
                        log("Sony: PTP live-view probe FAILED — ${controller.lastLiveViewDiagnostic}")
                    }
                }
            }.start()
        }

        sonyLiveStreamButton.setOnClickListener {
            if (sonyLiveDesired || sonyLiveRunning) {
                stopSonyLiveView(userRequested = true)
            } else {
                sonyLiveDesired = true
                startSonyLiveView()
            }
        }
        sonyAutoTrackButton.setOnClickListener {
            setSonyAutoTracking(!sonyAutoTracking)
        }

        // Cold-start self-heal: credentials are already provisioned on this
        // dedicated capture tablet. Restore the Sony control session without
        // consuming its single command channel with a preview request before
        // the camera is confirmed on its shooting screen. Physical motion and
        // Live View remain explicitly gated and default OFF.
        val provisionedIp = ipInput.text.toString().trim()
        val provisionedUser = sshUserInput.text.toString().trim()
        val provisionedPassword = sshPasswordInput.text.toString()
        if (provisionedIp.isNotEmpty() && provisionedUser.isNotEmpty() && provisionedPassword.isNotEmpty()) {
            sonyConnectionSpec = SonyConnectionSpec(
                provisionedIp, provisionedUser, provisionedPassword
            )
            sonyLiveDesired = false
            sonyConnectionGeneration += 1L
            val generation = sonyConnectionGeneration
            handler.postDelayed({ connectSonyOnce(generation) }, 500L)
        }
    }

    /** One connection attempt. Every failure is fully closed inside
     * SonyPtpIpController, then retried with bounded exponential backoff. */
    private fun connectSonyOnce(generation: Long) {
        val spec = sonyConnectionSpec ?: return
        if (!sonyRecoveryEnabled || generation != sonyConnectionGeneration || sonyConnectInFlight) return
        cancelSonyReconnect()
        sonyConnectInFlight = true
        sonyController?.disconnect()
        sonyController = null
        sonyStatusText.text = "Connecting to ${spec.ip}..."
        log("Sony: authenticating SSH to ${spec.ip} as ${spec.sshUser}")
        thread(name = "SonyReconnect") {
            val controller = SonyPtpIpController()
            val ok = controller.connectBlocking(spec.ip, spec.sshUser, spec.sshPassword)
            handler.post {
                sonyConnectInFlight = false
                if (!sonyRecoveryEnabled || generation != sonyConnectionGeneration) {
                    controller.disconnect()
                    return@post
                }
                if (ok) {
                    sonyController = controller
                    sonyStatusText.text = "Connected -- ${spec.ip}"
                    log("Sony: PTP-IP-over-SSH handshake succeeded")
                    if (sonyLiveDesired) startSonyLiveView()
                } else {
                    controller.disconnect()
                    sonyStatusText.text = "Camera unavailable — recovering"
                    scheduleSonyReconnect("handshake failed")
                }
            }
        }
    }

    private fun scheduleSonyReconnect(reason: String) {
        if (!sonyRecoveryEnabled || sonyConnectionSpec == null) return
        if (sonyReconnectRunnable != null || sonyConnectInFlight) return
        sonyTrackingGimbal.stopAndReturnToCenter()
        sonyController?.disconnect()
        sonyController = null
        val generation = sonyConnectionGeneration
        val delayMs = minOf(15_000L, 1_000L * (1L shl minOf(sonyReconnectAttempt, 4)))
        sonyReconnectAttempt += 1
        sonyStatusText.text = "Recovering Sony in ${delayMs / 1_000}s"
        log("Sony: $reason; automatic reconnect in ${delayMs}ms")
        val runnable = Runnable {
            sonyReconnectRunnable = null
            connectSonyOnce(generation)
        }
        sonyReconnectRunnable = runnable
        handler.postDelayed(runnable, delayMs)
    }

    private fun cancelSonyReconnect() {
        sonyReconnectRunnable?.let(handler::removeCallbacks)
        sonyReconnectRunnable = null
    }

    private fun startSonyLiveView() {
        val controller = sonyController
        if (controller == null || !controller.isConnected) {
            sonyLiveDesired = true
            scheduleSonyReconnect("Live View requested while disconnected")
            return
        }
        if (sonyLiveRunning) return
        sonyLiveDesired = true
        controller.setLiveViewStreaming(true)
        val generation = sonyLiveGeneration + 1L
        sonyLiveGeneration = generation
        sonyLiveRunning = true
        sonyGoldServo.reset()
        sonyGoldTargetDetector.reset()
        sonyFrameCount = 0
        sonyAnalysisFrameId = 0L
        sonyFrameWindowStarted = SystemClock.elapsedRealtime()
        sonyLastFrameLogAt = 0
        sonyLiveViewContainer.visibility = View.VISIBLE
        sonyLiveStreamButton.text = "Stop live view"
        sonyTrackingStatusText.text = "Starting Sony Live View…"
        if (sonyAutoTracking) ensureSonyTrackingGimbal()

        sonyLiveThread = thread(start = true, name = "SonyLiveView") {
            var consecutiveFailures = 0
            while (sonyLiveRunning && generation == sonyLiveGeneration &&
                controller === sonyController && controller.isConnected
            ) {
                val frameStarted = SystemClock.elapsedRealtime()
                try {
                    val jpeg = controller.fetchLiveViewJpeg()
                    val fetchedAt = SystemClock.elapsedRealtime()
                    if (jpeg == null) {
                        consecutiveFailures += 1
                        if (consecutiveFailures == 5) log("Sony Live View: 5 consecutive frame failures")
                        if (consecutiveFailures >= SONY_LIVE_FAILURES_BEFORE_RECONNECT) {
                            log("Sony Live View: frame source unhealthy; rebuilding camera session")
                            controller.disconnect()
                            break
                        }
                        Thread.sleep(40L)
                        continue
                    }
                    val bitmap = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size)
                    val decodedAt = SystemClock.elapsedRealtime()
                    if (bitmap == null) {
                        consecutiveFailures += 1
                        Thread.sleep(40L)
                        continue
                    }
                    // A completed handshake alone is not a healthy camera
                    // path. Reset the recovery backoff only after the first
                    // decodable Live View frame arrives.
                    sonyReconnectAttempt = 0
                    consecutiveFailures = 0
                    val analysis = sonyGoldTargetDetector.analyse(bitmap)
                    val analysedAt = SystemClock.elapsedRealtime()
                    val target = analysis.target
                    sonyAnalysisFrameId += 1L
                    val observation = target?.let {
                        SonyGoldServoController.Observation(
                            frameId = sonyAnalysisFrameId,
                            bounds = it.bounds,
                            pointCount = it.points.size,
                            scale = it.scale,
                            sharpness = it.sharpness
                        )
                    }
                    val now = SystemClock.elapsedRealtime()
                    val decision = if (sonyAutoTracking) {
                        sonyGoldServo.onFrame(
                            observation,
                            now,
                            sonyTrackingGimbal.isReady,
                            sonyTrackingGimbal.isMoving
                        )
                    } else {
                        SonyGoldServoController.Decision(
                            command = null,
                            status = if (target != null) {
                                "Isolated gold ready — auto tracking off"
                            } else {
                                "Place one gold item inside cyan guide"
                            },
                            centerX = target?.bounds?.let { (it.x0 + it.x1) / 2f },
                            centerY = target?.bounds?.let { (it.y0 + it.y1) / 2f },
                            coverage = target?.scale ?: 0f,
                            detectionStable = target != null
                        )
                    }

                    applySonyTrackingCommand(controller, decision.command)
                    sonyFrameCount += 1
                    val elapsedWindow = (now - sonyFrameWindowStarted).coerceAtLeast(1L)
                    val fps = sonyFrameCount * 1000f / elapsedWindow
                    val goldPoints = target?.points ?: emptyList()
                    enqueueSonyUiFrame(
                        SonyUiFrame(
                            generation = generation,
                            bitmap = bitmap,
                            goldPoints = goldPoints,
                            target = target,
                            decision = decision,
                            candidateCount = analysis.candidateCount,
                            fps = fps,
                            networkMs = fetchedAt - frameStarted,
                            decodeMs = decodedAt - fetchedAt,
                            analysisMs = analysedAt - decodedAt
                        )
                    )

                    if (now - sonyLastFrameLogAt >= 2_000L) {
                        sonyLastFrameLogAt = now
                        log(
                            "Sony Live View: ${bitmap.width}x${bitmap.height} ${"%.1f".format(fps)}fps strictGold=${goldPoints.size} " +
                                "scale=${"%.3f".format(decision.coverage)} " +
                                "sharp=${"%.4f".format(target?.sharpness ?: 0f)} " +
                                "candidates=${analysis.candidateCount} status=${decision.status}"
                        )
                    }
                    if (elapsedWindow >= 5_000L) {
                        sonyFrameCount = 0
                        sonyFrameWindowStarted = now
                    }

                    // No pacing sleep: fetchLiveViewJpeg() now blocks until the
                    // pump has a genuinely NEW frame, so this loop self-paces
                    // to the camera's real cadence instead of capping itself.
                } catch (_: InterruptedException) {
                    break
                } catch (e: Exception) {
                    consecutiveFailures += 1
                    log("Sony Live View frame failed: ${e.message}")
                    try { Thread.sleep(150L) } catch (_: InterruptedException) { break }
                }
            }
            handler.post {
                if (generation == sonyLiveGeneration) sonyLiveThread = null
                if (generation == sonyLiveGeneration && sonyLiveRunning && !controller.isConnected) {
                    sonyLiveRunning = false
                    sonyLiveStreamButton.text = "Start live view"
                    sonyTrackingStatusText.text = "Sony connection lost — recovering"
                    scheduleSonyReconnect("Live View connection lost")
                }
            }
        }
        log("Sony Live View started")
    }

    private fun stopSonyLiveView(userRequested: Boolean = true) {
        sonyLiveRunning = false
        if (userRequested) sonyLiveDesired = false
        sonyController?.setLiveViewStreaming(false)
        sonyLiveGeneration += 1L
        sonyLiveThread?.interrupt()
        sonyLiveThread = null
        sonyLatestUiFrame.set(null)
        sonyGoldServo.reset()
        sonyGoldTargetDetector.reset()
        sonyGoldOverlay.updateTarget(
            emptyList(), null, SONY_ACQUISITION_GUIDE,
            1, 1, 0, confirmed = false
        )
        if (::sonyLiveStreamButton.isInitialized) sonyLiveStreamButton.text = "Start live view"
        if (::sonyTrackingStatusText.isInitialized) sonyTrackingStatusText.text = "Sony Live View stopped"
        log("Sony Live View stopped")
    }

    private fun enqueueSonyUiFrame(frame: SonyUiFrame) {
        sonyLatestUiFrame.set(frame)
        if (sonyUiUpdatePending.compareAndSet(false, true)) {
            handler.post(sonyUiDrainRunnable)
        }
    }

    private fun renderSonyUiFrame(frame: SonyUiFrame) {
        val bitmap = frame.bitmap
        val target = frame.target
        val decision = frame.decision
        sonyLiveViewImage.setImageBitmap(bitmap)
        sonyGoldOverlay.updateTarget(
            points = frame.goldPoints,
            target = target?.bounds,
            guide = SONY_ACQUISITION_GUIDE,
            sourceWidth = bitmap.width,
            sourceHeight = bitmap.height,
            rotationDegrees = 0,
            confirmed = decision.detectionStable
        )
        val center = if (decision.centerX != null && decision.centerY != null) {
            " center=%.2f,%.2f".format(decision.centerX, decision.centerY)
        } else ""
        val detail = target?.let {
            " sharp=%.4f dark=%.2f highlight=%.2f".format(
                it.sharpness, it.darkSurroundFraction, it.highlightFraction
            )
        } ?: ""
        sonyTrackingStatusText.text =
            "${decision.status}\n${bitmap.width}×${bitmap.height}  %.1f fps  net=%dms decode=%dms analyse=%dms  strictGold=%d  scale=%.3f%s%s  candidates=%d  gimbal=%s".format(
                frame.fps,
                frame.networkMs,
                frame.decodeMs,
                frame.analysisMs,
                frame.goldPoints.size,
                decision.coverage,
                center,
                detail,
                frame.candidateCount,
                if (sonyTrackingGimbal.isReady) "ready" else "not connected"
            )
    }

    private fun setSonyAutoTracking(enabled: Boolean) {
        sonyAutoTracking = enabled
        sonyGoldServo.reset()
        sonyAutoTrackButton.text = if (enabled) "Auto gold track: ON" else "Auto gold track: off"
        if (enabled) {
            if (!sonyLiveRunning) startSonyLiveView()
            ensureSonyTrackingGimbal()
            log("Sony auto gold tracking enabled: steer first, optical zoom only after centering")
        } else {
            sonyTrackingGimbal.stopAndReturnToCenter()
            log("Sony auto gold tracking disabled")
        }
    }

    private fun applySonyTrackingCommand(
        controller: SonyPtpIpController,
        command: SonyGoldServoController.Command?
    ) {
        if (!sonyAutoTracking || command == null) return
        when (command) {
            is SonyGoldServoController.Command.Pan -> handler.post {
                if (!sonyAutoTracking || !sonyTrackingGimbal.isReady || sonyTrackingGimbal.isMoving) return@post
                val axis = DumlProtocol.AXIS_CENTER + command.sign * SONY_GIMBAL_DEFLECTION
                sonyTrackingGimbal.moveOut(axis3 = axis, durationMs = command.durationMs) {}
            }
            is SonyGoldServoController.Command.Tilt -> handler.post {
                if (!sonyAutoTracking || !sonyTrackingGimbal.isReady || sonyTrackingGimbal.isMoving) return@post
                val axis = DumlProtocol.AXIS_CENTER + command.sign * SONY_GIMBAL_DEFLECTION
                sonyTrackingGimbal.moveOut(axis1 = axis, durationMs = command.durationMs) {}
            }
            is SonyGoldServoController.Command.Zoom -> {
                // Same PTP worker as frame fetching: no concurrent camera
                // transaction, and the next frame measures the real result.
                controller.driveZoom(command.tele, command.durationMs)
            }
            is SonyGoldServoController.Command.Focus -> {
                // S1/half-press only. SonyPtpIpController guarantees that
                // this path never sends the capture/S2 property.
                val ok = controller.driveAutoFocus(command.durationMs)
                if (!ok) log("Sony autofocus command was not acknowledged")
            }
        }
    }

    private fun ensureSonyTrackingGimbal() {
        if (sonyTrackingGimbal.isReady || sonyGimbalConnecting) return
        val permissions = if (Build.VERSION.SDK_INT >= 31) {
            arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
        }
        val missing = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            pendingSonyGimbalConnect = true
            requestPermissions.launch(missing.toTypedArray())
            return
        }
        connectSonyTrackingGimbal()
    }

    private fun connectSonyTrackingGimbal() {
        if (sonyTrackingGimbal.isReady || sonyGimbalConnecting) return
        sonyGimbalConnecting = true
        log("Sony tracking: connecting to RSC 2 gimbal…")
        sonyTrackingGimbal.connect(this) { success ->
            sonyGimbalConnecting = false
            log(if (success) "Sony tracking: RSC 2 ready" else "Sony tracking: RSC 2 connection failed")
        }
    }

    companion object {
        private const val SONY_LIVE_FRAME_INTERVAL_MS = 33L
        private const val SONY_LIVE_FAILURES_BEFORE_RECONNECT = 12
        private const val SONY_GIMBAL_DEFLECTION = 120
        private val SONY_ACQUISITION_GUIDE = MaterialDetector.Bounds(
            SonyGoldTargetDetector.ACQUIRE_LEFT,
            SonyGoldTargetDetector.ACQUIRE_TOP,
            SonyGoldTargetDetector.ACQUIRE_RIGHT,
            SonyGoldTargetDetector.ACQUIRE_BOTTOM
        )
    }

    private fun requestPermissionsThenScan() {
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
        if (missing.isEmpty()) startScan() else requestPermissions.launch(missing.toTypedArray())
    }

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val device = result.device
            if (!seenAddresses.add(device.address)) return
            val name = try { device.name } catch (e: SecurityException) { null } ?: "(unnamed)"
            log("Found: $name  ${device.address}  rssi=${result.rssi}")
            addDeviceButton(device, name)
        }

        override fun onScanFailed(errorCode: Int) {
            log("Scan failed: errorCode=$errorCode")
            scanning = false
        }
    }

    private fun startScan() {
        if (bluetoothAdapter == null || !bluetoothAdapter.isEnabled) {
            log("Bluetooth is off or unavailable on this device.")
            return
        }
        deviceListContainer.removeAllViews()
        seenAddresses.clear()
        scanning = true
        statusText.text = "Scanning..."
        log("Scanning for 12s...")
        try {
            bluetoothAdapter.bluetoothLeScanner?.startScan(scanCallback)
        } catch (e: SecurityException) {
            log("Missing permission to scan: ${e.message}")
            return
        }
        handler.postDelayed({
            if (scanning) {
                try { bluetoothAdapter.bluetoothLeScanner?.stopScan(scanCallback) } catch (_: SecurityException) {}
                scanning = false
                statusText.text = "Scan complete -- ${seenAddresses.size} device(s) found"
                log("Scan complete.")
            }
        }, 12_000L)
    }

    private fun addDeviceButton(device: BluetoothDevice, name: String) {
        val button = Button(this).apply {
            text = "$name  (${device.address})"
            setOnClickListener { connectTo(device) }
        }
        deviceListContainer.addView(button)
    }

    private fun connectTo(device: BluetoothDevice) {
        log("Connecting to ${device.address}...")
        statusText.text = "Connecting to ${device.address}..."
        try {
            gatt = device.connectGatt(this, false, gattCallback)
        } catch (e: SecurityException) {
            log("Missing BLUETOOTH_CONNECT permission: ${e.message}")
        }
    }

    private val gattCallback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            when (newState) {
                BluetoothProfile.STATE_CONNECTED -> {
                    log("Connected (status=$status). Discovering services...")
                    handler.post { statusText.text = "Connected -- discovering services" }
                    try { g.discoverServices() } catch (e: SecurityException) { log("discoverServices denied: ${e.message}") }
                }
                BluetoothProfile.STATE_DISCONNECTED -> {
                    log("Disconnected (status=$status).")
                    handler.post {
                        statusText.text = "Disconnected"
                        characteristicListContainer.removeAllViews()
                    }
                }
            }
        }

        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
            handler.post { characteristicListContainer.removeAllViews() }
            log("--- GATT services (status=$status) ---")
            for (service in g.services) {
                log("Service: ${service.uuid}")
                for (characteristic in service.characteristics) {
                    val props = describeProperties(characteristic.properties)
                    log("  Characteristic: ${characteristic.uuid}  [$props]")
                    for (descriptor in characteristic.descriptors) {
                        log("    Descriptor: ${descriptor.uuid}")
                    }
                    val writable = characteristic.properties and
                        (BluetoothGattCharacteristic.PROPERTY_WRITE or BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE) != 0
                    if (writable) {
                        handler.post { addCharacteristicButton(characteristic) }
                    }
                    val notifiable = characteristic.properties and
                        (BluetoothGattCharacteristic.PROPERTY_NOTIFY or BluetoothGattCharacteristic.PROPERTY_INDICATE) != 0
                    if (notifiable) {
                        subscribeToNotifications(g, characteristic)
                    }
                }
            }
            log("--- end of GATT services ---")
            handler.post { statusText.text = "Connected -- ${characteristicListContainer.childCount} writable characteristic(s)" }
        }

        override fun onCharacteristicWrite(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) {
            log("Write to ${characteristic.uuid} -> status=$status (${if (status == 0) "SUCCESS" else "FAILED"})")
        }

        // Two overloads exist because the byte[]-value version was only
        // added in API 33; onDestroy/minSdk 26 means the pre-33 deprecated
        // one still needs handling on most real devices in the field.
        override fun onCharacteristicChanged(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray) {
            logNotification(characteristic, value)
        }

        @Suppress("DEPRECATION")
        override fun onCharacteristicChanged(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
            if (Build.VERSION.SDK_INT < 33) logNotification(characteristic, characteristic.value ?: ByteArray(0))
        }

        override fun onDescriptorWrite(g: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) {
            log("Notify subscribe on ${descriptor.characteristic.uuid} -> status=$status (${if (status == 0) "SUCCESS" else "FAILED"})")
        }
    }

    private fun logNotification(characteristic: BluetoothGattCharacteristic, value: ByteArray) {
        val hex = value.joinToString(" ") { "%02X".format(it) }
        log(">>> NOTIFY from ${characteristic.uuid}: $hex")
    }

    /** Subscribes locally (setCharacteristicNotification) AND tells the
     * peripheral to actually start sending (writing the standard Client
     * Characteristic Configuration descriptor, 0x2902) -- the first half
     * alone is a common no-op mistake; without the descriptor write the
     * device never turns notifications on at its end. */
    @Suppress("DEPRECATION")
    private fun subscribeToNotifications(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
        try {
            g.setCharacteristicNotification(characteristic, true)
            val cccd = characteristic.getDescriptor(
                java.util.UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
            ) ?: return
            val value = if (characteristic.properties and BluetoothGattCharacteristic.PROPERTY_NOTIFY != 0) {
                BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
            } else {
                BluetoothGattDescriptor.ENABLE_INDICATION_VALUE
            }
            cccd.value = value
            g.writeDescriptor(cccd)
            log("Subscribing to notifications on ${characteristic.uuid}...")
        } catch (e: SecurityException) {
            log("Missing permission to subscribe: ${e.message}")
        }
    }

    private fun describeProperties(props: Int): String {
        val parts = mutableListOf<String>()
        if (props and BluetoothGattCharacteristic.PROPERTY_READ != 0) parts += "READ"
        if (props and BluetoothGattCharacteristic.PROPERTY_WRITE != 0) parts += "WRITE"
        if (props and BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE != 0) parts += "WRITE_NO_RESPONSE"
        if (props and BluetoothGattCharacteristic.PROPERTY_NOTIFY != 0) parts += "NOTIFY"
        if (props and BluetoothGattCharacteristic.PROPERTY_INDICATE != 0) parts += "INDICATE"
        return if (parts.isEmpty()) "none" else parts.joinToString(",")
    }

    private fun addCharacteristicButton(characteristic: BluetoothGattCharacteristic) {
        val button = Button(this).apply {
            text = characteristic.uuid.toString()
            setOnClickListener {
                selectedCharacteristic = characteristic
                Toast.makeText(this@BleDiagnosticsActivity, "Selected ${characteristic.uuid}", Toast.LENGTH_SHORT).show()
                log("Selected characteristic for writes: ${characteristic.uuid}")
            }
        }
        characteristicListContainer.addView(button)
    }

    private fun parseHexInput(): ByteArray? {
        val hex = hexBytesInput.text.toString().trim()
        val bytes = try {
            hex.split(Regex("[\\s,]+")).filter { it.isNotBlank() }
                .map { it.removePrefix("0x").removePrefix("0X").toInt(16).toByte() }
                .toByteArray()
        } catch (e: Exception) {
            log("Could not parse hex bytes '$hex': ${e.message}")
            return null
        }
        if (bytes.isEmpty()) {
            log("Enter hex bytes first, e.g. 55 AA 01")
            return null
        }
        return bytes
    }

    @Suppress("DEPRECATION")
    private fun writeBytesToSelected(bytes: ByteArray, quiet: Boolean = false): Boolean {
        val characteristic = selectedCharacteristic
        val g = gatt
        if (characteristic == null || g == null) {
            log("No characteristic selected -- connect and tap a writable characteristic first.")
            return false
        }
        // A characteristic that only advertises WRITE_NO_RESPONSE (like
        // FFF3/FFF5 here) needs that write type set EXPLICITLY -- the
        // default is WRITE_TYPE_DEFAULT (with-response), and sending that
        // to a no-response-only characteristic is a well-known silent
        // failure on several Android BLE stacks: writeCharacteristic()
        // returns true, no exception, no error, the peripheral just never
        // receives it. This is almost certainly why "00" produced nothing.
        val writeType = if (characteristic.properties and BluetoothGattCharacteristic.PROPERTY_WRITE != 0) {
            BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        } else {
            BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
        }
        characteristic.writeType = writeType
        if (!quiet) {
            log("Writing ${bytes.joinToString(" ") { "%02X".format(it) }} to ${characteristic.uuid}")
        }
        characteristic.value = bytes
        return try {
            val ok = g.writeCharacteristic(characteristic)
            if (!quiet) log(if (ok) "writeCharacteristic() accepted" else "writeCharacteristic() returned FALSE (queue busy or invalid state)")
            ok
        } catch (e: SecurityException) {
            log("Missing BLUETOOTH_CONNECT permission to write: ${e.message}")
            false
        }
    }

    private fun sendHexToSelected() {
        val bytes = parseHexInput() ?: return
        writeBytesToSelected(bytes)
    }

    /**
     * Replays a captured command repeatedly, matching the real ~200ms cadence
     * DJI's own Ronin app uses while a joystick is held (confirmed from the
     * captured btsnoop log) -- a single write of a deflected value is
     * unlikely to produce visible motion since the real protocol appears to
     * treat each frame as "move toward this target for this tick", not "go
     * to this position and stay". This is the actual reproduction of a held
     * stick, not a new guess at the protocol.
     */
    /** Cancels any in-flight repeat-send loop -- must be called before
     * starting a new one, and by every stop/neutral action, or leftover
     * scheduled sends keep firing after a "stop" and undo it. */
    private fun cancelActiveRepeat() {
        activeRepeatRunnable?.let { handler.removeCallbacks(it) }
        activeRepeatRunnable = null
    }

    private fun sendHexRepeatedly(count: Int = 15, intervalMs: Long = 200L) {
        val bytes = parseHexInput() ?: return
        cancelActiveRepeat()
        log("Sending ${bytes.joinToString(" ") { "%02X".format(it) }} x$count @ ${intervalMs}ms -- watch the gimbal now")
        var sent = 0
        val runnable = object : Runnable {
            override fun run() {
                if (sent >= count) {
                    log("Repeat send complete ($sent sent).")
                    activeRepeatRunnable = null
                    return
                }
                writeBytesToSelected(bytes, quiet = true)
                sent += 1
                handler.postDelayed(this, intervalMs)
            }
        }
        activeRepeatRunnable = runnable
        handler.post(runnable)
    }

    private fun readAxisInputs(): Triple<Int, Int, Int>? {
        return try {
            val a1 = axis1Input.text.toString().trim().toInt()
            val a2 = axis2Input.text.toString().trim().toInt()
            val a3 = axis3Input.text.toString().trim().toInt()
            Triple(a1, a2, a3)
        } catch (e: Exception) {
            log("Enter valid integer axis values (default 1024 = center).")
            null
        }
    }

    /**
     * Builds a real, checksummed DUML joystick frame for arbitrary axis
     * values (see DumlProtocol.kt) instead of replaying a fixed captured
     * byte string -- this is what makes arbitrary-angle calibration
     * possible later, not just the couple of values we happened to capture.
     */
    private fun sendCustomJoystickFrame(repeat: Boolean) {
        val (a1, a2, a3) = readAxisInputs() ?: return
        cancelActiveRepeat()
        val count = if (repeat) 15 else 1
        log("Building frames axis=($a1,$a2,$a3) x$count -- watch the gimbal now")
        var sent = 0
        val runnable = object : Runnable {
            override fun run() {
                if (sent >= count) {
                    if (repeat) log("Repeat send complete ($sent sent).")
                    activeRepeatRunnable = null
                    return
                }
                val frame = DumlProtocol.buildJoystickFrame(a1, a2, a3, duMLSeq)
                duMLSeq += 1
                writeBytesToSelected(frame, quiet = repeat)
                sent += 1
                handler.postDelayed(this, 200L)
            }
        }
        if (repeat) activeRepeatRunnable = runnable
        handler.post(runnable)
    }

    private fun sendNeutral() {
        // Stop must win outright: kill any pending repeat sends FIRST, then
        // send neutral last so nothing queued afterward can override it.
        cancelActiveRepeat()
        val frame = DumlProtocol.neutralFrame(duMLSeq)
        duMLSeq += 1
        log("Sending neutral (stop)")
        writeBytesToSelected(frame)
    }

    private fun disconnect() {
        cancelActiveRepeat()
        try {
            gatt?.disconnect()
            gatt?.close()
        } catch (e: SecurityException) {
            log("Missing permission to disconnect: ${e.message}")
        }
        gatt = null
        selectedCharacteristic = null
        statusText.text = "Disconnected"
        log("Disconnected by user.")
    }

    private fun log(message: String) {
        handler.post {
            logText.append("$message\n")
            logScroll.post { logScroll.fullScroll(View.FOCUS_DOWN) }
        }
    }

    override fun onDestroy() {
        sonyRecoveryEnabled = false
        sonyConnectionGeneration += 1L
        cancelSonyReconnect()
        stopSonyLiveView()
        sonyTrackingGimbal.disconnect()
        super.onDestroy()
        try {
            if (scanning) bluetoothAdapter.bluetoothLeScanner?.stopScan(scanCallback)
            // disconnect() before close() -- close() alone just tears down
            // the local client object without necessarily telling the
            // peripheral the link is ending, which can leave the RSC 2
            // thinking this screen still holds its single connection slot
            // and refusing a new connection from the main capture screen.
            gatt?.disconnect()
            gatt?.close()
        } catch (_: SecurityException) {}
        // Unbind the process's network binding to the camera's WiFi AP --
        // otherwise every other network call in this app (uploads, LAN
        // traffic) keeps trying to route over a network this screen no
        // longer needs, after the operator navigates away.
        sonyController?.disconnect()
        sonyController = null
        sonyWifi.unbind()
    }
}
