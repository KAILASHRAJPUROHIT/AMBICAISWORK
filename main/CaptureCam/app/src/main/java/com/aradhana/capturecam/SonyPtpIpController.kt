package com.aradhana.capturecam

import android.graphics.BitmapFactory
import android.os.Process
import android.util.Log
import com.jcraft.jsch.Channel
import com.jcraft.jsch.ChannelDirectTCPIP
import com.jcraft.jsch.JSch
import com.jcraft.jsch.Session
import java.io.BufferedInputStream
import java.io.InputStream
import java.io.OutputStream
import java.net.URI
import java.net.SocketTimeoutException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference
import kotlin.concurrent.thread

data class SonyQualitySettings(
    val exposureMode: Int,
    val iso: Int,
    val whiteBalance: Int,
    val stillFileFormat: Int? = null,
    val jpegQuality: Int? = null,
    val imageSize: Int? = null,
    val stillImageTransferSize: Int? = null,
    val rawFileType: Int? = null,
    val aspectRatio: Int? = null,
    val dynamicRangeOptimizer: Int? = null,
    val creativeLook: Int? = null,
    val fNumberTimes100: Int? = null,
    val shutterNumerator: Int? = null,
    val shutterDenominator: Int? = null,
    val exposureCompensationMilliEv: Int = 0,
    val focusMode: Int = 0x8004,
    val focusArea: Int = 259,
    val exposureMeteringMode: Int? = null
)

/**
 * PTP-IP client for Sony Alpha-family cameras with "Access Authentication"
 * (confirmed target: ZV-E10 II). Sony's official Camera Remote SDK does
 * NOT support Android (macOS/Windows-x86/Linux only, confirmed against
 * Sony's own SDK docs) -- this talks to the camera directly instead.
 *
 * CONFIRMED LIVE 2026-08-23 against a real ZV-E10 II (not speculative):
 * this camera generation does NOT expose PTP-IP on a plain TCP port. Its
 * "Remote Shoot Function" opens an SSH server (OpenSSH_7.9, port 22)
 * instead, authenticated with the username/password/fingerprint shown on
 * the camera's own MENU -> Network -> Network Option -> Access Authen.
 * Info screen. Sony's own docs confirm this is intentional: "communication
 * data can be encrypted over an SSH connection" for cameras with access
 * authentication. The SSH account only permits port-forwarding (shell/exec
 * channels are rejected with "Administratively prohibited"), and only ONE
 * destination is allowed: a "direct-tcpip" channel to literally the string
 * "localhost" (not "127.0.0.1") on port 15740 -- every other host/port
 * combination tried was rejected with the same "Administratively
 * prohibited" error. That tunneled channel carries completely standard
 * PTP-IP framing (CIPA DC-X005) once you include a 4-byte protocol-version
 * field after the friendly name in Init Command Request/Ack that most
 * summarized references omit -- omitting it causes the camera to silently
 * close the channel with no response, which cost real debugging time
 * before comparing byte counts against a working Canon EOS capture
 * (julianschroden.com's PTP-IP writeup) and finding the 4 missing bytes.
 *
 * The Sony-specific SDIO extension opcodes/property codes riding on top of
 * this tunneled PTP-IP channel are reverse engineered the same way as
 * before this SSH discovery (frank26080115/alpha-fairy, olkham/pysonycam)
 * -- see their sourcing note below. Only the TRANSPORT changed for this
 * camera generation; the SDIO command/property layer itself is unverified
 * against a live capture-and-verify beyond the handshake at the time of
 * writing and may need adjustment.
 */
class SonyPtpIpController {

    companion object {
        private const val TAG = "SonyPtpIp"

        // The camera's SSH account only allows forwarding to exactly this
        // host string + port -- see class doc. Using "127.0.0.1" instead
        // of the literal string "localhost" was rejected, so don't
        // "simplify" this to an IP constant.
        private const val TUNNEL_HOST = "localhost"
        private const val TUNNEL_PORT = 15740
        private const val LIVE_VIEW_REMOTE_PORT = 60152
        private const val SSH_CONTROL_WINDOW_BYTES = 4 * 1024 * 1024
        private const val SSH_LIVE_VIEW_WINDOW_BYTES = 1024 * 1024
        private const val SSH_CHANNEL_PACKET_BYTES = 64 * 1024
        private const val PTP_READ_TIMEOUT_MS = 12_000L
        private const val LOG_ALL_CHUNKS_UNDER = 8
        private const val LOG_CHUNK_STRIDE = 40
        private const val LIVE_VIEW_READ_TIMEOUT_MS = 8_000L
        private const val QUALITY_PROPERTY_SETTLE_TIMEOUT_MS = 800L
        private const val LIVE_VIEW_MAX_JPEG_BYTES = 4 * 1024 * 1024
        private const val LIVE_VIEW_MAX_FOCAL_INFO_BYTES = 512 * 1024
        private const val LIVE_VIEW_MAX_DATASET_BYTES = 5 * 1024 * 1024
        private const val LIVE_VIEW_READ_CHUNK_BYTES = 64 * 1024
        // HTTP 503 is a valid short transient while Sony restarts its local
        // producer or moves the power zoom. Give that producer 3.2s, then
        // let SonyProductionCamera replace the whole SSH/PTP session. The
        // previous 40 x 400ms budget held production for 16-40s even though
        // a complete session replacement takes about 1.4s.
        private const val LIVE_VIEW_MAX_HTTP_REJECTS = 8
        // One failed stream may be reopened once. If that replacement also
        // fails before delivering a frame, the session is not useful; fail
        // the pump so the owning layer performs a full reconnect.
        private const val LIVE_VIEW_MAX_TRANSPORT_FAILURES = 2
        private const val LIVE_VIEW_REOPEN_RETRY_DELAY_MS = 400L
        // More than two 25fps frame periods. Count as a real source stall,
        // not ordinary network jitter.
        private const val LIVE_VIEW_SLOW_GAP_MS = 80L
        // Healthy 25fps source cadence is ~40ms. Bound a blocked HTTP body
        // read without disturbing the separate persistent PTP control lane.
        // The single-flight recovery gate below guarantees this watchdog can
        // close a stuck channel only once per recovery attempt.
        // Raised from 750ms (2026-08-29 fix): this code only started running
        // live against the real camera today (it sat on an unmerged branch
        // since 2026-08-26) and immediately produced a reconnect loop that
        // was never present before. Live-confirmed: real stalls measured
        // consistently at 825-829ms, always just barely over the old 750ms
        // threshold, during ordinary AF-scan/zoom operations -- not a dead
        // connection, a frame that was one moment away from arriving. The
        // watchdog killed a healthy channel right as it was about to
        // recover, and that forced closure is what produced the resulting
        // "HTTP chunk header ended early" read failure -- a self-inflicted
        // error, not a real network fault. 2000ms comfortably clears the
        // observed real-world gap while still catching a genuinely dead
        // multi-second stall.
        private const val LIVE_VIEW_STALL_TIMEOUT_MS = 2_000L
        private const val TRANSPORT_HEALTH_POLL_MS = 250L
        private const val TRANSPORT_HEALTH_LOG_MS = 15_000L
        private const val PRODUCTION_ZOOM_MIN_RATIO = 1f
        private const val PRODUCTION_ZOOM_MAX_RATIO = 3.125f
        private const val PRODUCTION_ZOOM_FULL_TRAVEL_MS = 1_650f
        private const val ZOOM_HTTP_SETTLE_MS = 900L

        // --- PTP-IP packet types (CIPA DC-X005 public spec) ---
        private const val PKT_INIT_COMMAND_REQUEST = 1
        private const val PKT_INIT_COMMAND_ACK = 2
        private const val PKT_INIT_EVENT_REQUEST = 3
        private const val PKT_INIT_EVENT_ACK = 4
        private const val PKT_OPERATION_REQUEST = 6
        private const val PKT_OPERATION_RESPONSE = 7
        private const val PKT_EVENT = 8
        private const val PKT_START_DATA_PACKET = 9
        private const val PKT_DATA_PACKET = 10
        private const val PKT_END_DATA_PACKET = 12
        private const val PKT_PROBE_REQUEST = 13
        private const val PKT_PROBE_RESPONSE = 14

        // CIPA DC-X005 Operation Request data-phase values.  The old client
        // sent 0 for every operation, which is not a standard wire value.
        private const val DP_NO_DATA_OR_DATA_IN = 1
        private const val DP_DATA_OUT = 2

        // --- Standard PTP opcodes ---
        private const val PTP_OC_GetDeviceInfo = 0x1001
        private const val PTP_OC_OpenSession = 0x1002
        private const val PTP_OC_GetStorageIDs = 0x1004
        private const val PTP_OC_GetObjectHandles = 0x1007
        private const val PTP_OC_GetObjectInfo = 0x1008
        private const val PTP_OC_GetObject = 0x1009

        // Sony asynchronous events. libgphoto2's current Sony table confirms
        // C201=ObjectAdded, C202=ObjectRemoved, C203=DevicePropChanged and
        // C206=CapturedEvent. Older third-party tables swapped C201/C202.
        private const val PTP_EC_ObjectAdded = 0x4002
        private const val PTP_EC_SonyObjectAdded = 0xC201

        // --- Sony SDIO extension opcodes (reverse engineered, see class doc) ---
        private const val OC_SDIOConnect = 0x9201
        private const val OC_SDIOGetExtDeviceInfo = 0x9202
        private const val OC_SetControlDeviceA = 0x9205
        private const val OC_SetControlDeviceB = 0x9207
        private const val OC_SDIOGetAllExtDeviceInfo = 0x9209
        private const val OC_SDIOGetVendorCodeVersion = 0x9216

        const val PROP_AutoFocus = 0xD2C1        // S1 (half-press) -- 2=engage, 1=release
        const val PROP_Capture = 0xD2C2          // S2 (full-press) -- 2=engage, 1=release
        const val PROP_ISO = 0xD21E
        const val PROP_WhiteBalance = 0x5005
        const val PROP_FocusMode = 0x500A
        const val PROP_ExposureMeteringMode = 0x500B
        const val PROP_FocusIndication = 0xD213
        // Sony SDIO focus-mode values, cross-referenced from the same
        // alpha-fairy/pysonycam sources as the rest of this file's opcode
        // table (see class doc) -- MF=1, AF-S=2, AF-C=0x8004, AF-A=0x8005,
        // DMF=0x8006.
        const val AFMODE_AFS = 0x0002
        const val AFMODE_AFC = 0x8004
        const val PROP_ShutterSpeed = 0xD20D     // packed UINT32: numerator=high16, denominator=low16
        const val PROP_FNumber = 0x5007          // UINT16, value x100 (e.g. 450 = f/4.5)
        const val PROP_FocusArea = 0xD22C
        const val PROP_ExposureMode = 0x500E     // 0x0001=M 0x0002=P 0x0003=A 0x0004=S
        const val PROP_ZoomStep = 0xD2DD         // signed step; sign = direction
        const val PROP_ZoomScale = 0xD25C        // UINT32, value × 0.001
        const val PROP_ZoomOptical = 0xD25D      // read-only packed optical position; low byte 0..100
        const val PROP_ExposureCompensation = 0x5010
        const val PROP_DynamicRangeOptimizer = 0xD201
        const val PROP_ImageSize = 0xD203
        const val PROP_AspectRatio = 0xD211
        const val PROP_JpegQuality = 0xD252
        const val PROP_FileFormatStill = 0xD253
        const val PROP_CreativeLook = 0xD0FA
        const val PROP_RawFileType = 0xD288
        const val PROP_StillImageTransferSize = 0xD268
        const val PROP_FunctionOfTouchOperation = 0xD283
        const val PROP_RemoteTouchOperationEnable = 0xD284
        const val PROP_CancelRemoteTouchOperationEnable = 0xD285
        const val CONTROL_RemoteTouchOperation = 0xD2E4
        // Sony remote live-view transport priority. 0x01 = Display speed
        // (smaller JPEGs / higher source FPS), 0x02 = Image quality. Sony's
        // Creators' App exposes the same choice through its
        // LiveviewImageQualityController and sets it before opening HTTP.
        private const val PROP_LiveViewQuality = 0xD26A
        private const val LIVE_VIEW_QUALITY_DISPLAY_SPEED = 0x01
        // Standard/Sony DriveMode. Earlier code mislabeled this OperatingMode;
        // value 1 is single shot and 0x00010002 is Continuous Hi+.
        private const val PROP_DriveMode = 0x5013
        private const val PROP_ShootingFileInfo = 0xD215
        private const val PROP_LiveViewStatus = 0xD221
        private const val PROP_SaveMedia = 0xD222
        private const val PROP_PositionKey = 0xD25A
        private const val PROP_LiveViewUrl = 0xD278

        private const val DRIVE_SINGLE = 0x00000001
        private const val DRIVE_CONTINUOUS_HI_PLUS = 0x00010002
        private const val SAVE_MEDIA_HOST_AND_CAMERA = 0x0011
        private const val TRANSFER_SIZE_ORIGINAL = 1
        private const val TRANSFER_SIZE_2M = 2

        // Sony D2DD is a signed BYTE: positive=tele, negative=wide, 0=stop.
        // The old constants were reversed and were sent as UInt16, so the
        // button labelled Wide physically zoomed the lens in.
        const val ZOOM_TELE_STEP = 1
        const val ZOOM_WIDE_STEP = -1

        private const val SDI_VERSION_V3 = 0x012C // 300 -- matches pysonycam's SDI_VERSION_V3
        private const val SHOT_OBJECT_HANDLE = 0xFFFFC001.toInt()
        private const val LIVEVIEW_OBJECT_HANDLE = 0xFFFFC002.toInt()
    }

    @Volatile private var sshSession: Session? = null
    // Live View receives its own SSH transport/reader/window whenever the
    // camera accepts a second authenticated tunnel. PTP control and event
    // traffic then cannot consume the stream channel's flow-control window
    // or stall its JSch session reader. Shared-session fallback preserves
    // compatibility with bodies that permit only one SSH login.
    @Volatile private var liveViewSshSession: Session? = null
    private var controlChannel: ChannelDirectTCPIP? = null
    private var eventChannel: ChannelDirectTCPIP? = null
    @Volatile private var liveViewChannel: ChannelDirectTCPIP? = null
    private var controlOut: OutputStream? = null
    private var controlIn: InputStream? = null
    private var eventOut: OutputStream? = null
    private var eventIn: InputStream? = null
    @Volatile private var liveViewIn: InputStream? = null
    @Volatile private var liveViewOut: OutputStream? = null
    private var liveViewCarry = ByteArray(0)
    @Volatile private var liveViewUrl: String? = null
    // PTP spec reserves TransactionID 0 for the session-less OpenSession
    // call -- starting at 1 (as an earlier version of this file did) sent
    // OpenSession itself with txId=1, shifting every subsequent call's
    // txId by one. Confirmed live: the first real call after OpenSession
    // always succeeded regardless of which operation it was, but every
    // call after THAT consistently failed with SessionNotOpen -- exactly
    // the signature of a transaction-ID-sequencing mismatch the device
    // tolerates loosely at first and then rejects.
    private val transactionId = AtomicInteger(0)
    private val connectionEpoch = AtomicInteger(0)
    @Volatile private var sdiVendorCodeVersion = 0
    @Volatile private var remoteTouchFocusEnabled = false
    private val operationLock = Any()
    private val controlWriteLock = Any()
    private val liveViewLock = Any()

    /**
     * One decoded-ready Live View frame plus the metadata needed to reason
     * about its age. [sequence] increases monotonically per source frame, so
     * a consumer can tell "this is new" from "I already decoded this" without
     * comparing byte arrays.
     */
    data class LiveViewSample(
        val sequence: Long,
        val jpeg: ByteArray,
        val receivedAtNanos: Long,
        // Sony AF state embedded in every HTTP LiveViewDataset:
        // 2=AF-S focused, 3=AF-S failed, 5=AF-C tracking,
        // 6=AF-C focused, 7=AF-C failed/low contrast.
        val focusIndication: Int?
    )

    private data class LiveViewFrame(
        val jpeg: ByteArray,
        val focusIndication: Int?
    )

    // ---- Latest-only Live View pump -------------------------------------
    //
    // Confirmed live (2026-08-23/24): the old design fetched a frame, then
    // decoded, detected and rendered it BEFORE reading the socket again. The
    // camera keeps producing during that gap, so its buffers accumulated
    // whole frames and every subsequent read returned the OLDEST queued one.
    // That is what produced "roughly 19 FPS but 5+ seconds behind reality" --
    // throughput looked fine while the operator was watching the past. UI
    // coalescing could not fix it because the staleness was upstream of
    // decode.
    //
    // The fix is structural, not a tuning constant: exactly ONE thread owns
    // the HTTP stream and drains it at source speed, never pausing for
    // decode/detection. It keeps a single-slot AtomicReference of the newest
    // frame; older unconsumed frames are overwritten and counted as drops.
    // Consumers then always decode the newest scene. A slow consumer costs
    // dropped frames instead of accumulated latency, which is the correct
    // trade for a live viewfinder driving framing decisions.
    private val liveViewPumpLock = Any()
    private val liveViewSampleMonitor = Object()
    private val latestLiveViewSample = AtomicReference<LiveViewSample?>(null)
    private val liveViewSourceSequence = AtomicLong(0L)
    private val liveViewDecodedCount = AtomicLong(0L)
    private val liveViewDroppedBeforeDecode = AtomicLong(0L)
    private val liveViewReopenCount = AtomicLong(0L)
    private val liveViewWatchdogTripCount = AtomicLong(0L)
    private val liveViewSlowGapCount = AtomicLong(0L)
    private val lastLoggedFocalState = AtomicInteger(Int.MIN_VALUE)
    private val liveViewMaxGapMs = AtomicLong(0L)
    private val lastSlowDatasetLogAtNanos = AtomicLong(0L)
    @Volatile private var liveViewPumpRunning = false
    @Volatile private var liveViewPumpThread: Thread? = null
    @Volatile private var lastLiveViewFrameAtNanos = 0L
    @Volatile private var previousLiveViewSourceFrameAtNanos = 0L
    @Volatile private var lastServedSequence = 0L
    // Connection epoch the pump last gave up on. Confirmed live 2026-08-24:
    // without this latch, fetchLatestLiveViewSample() calling
    // startLiveViewPump() again immediately after "Live View pump stopped"
    // silently started a SECOND full 40-retry HTTP storm against the SAME
    // dead producer -- observed stacking to 28+s of continued 503s after the
    // first storm already gave up. startLiveViewPump() refuses to restart
    // for this epoch once it is set; a new connectBlocking() (which bumps
    // connectionEpoch) is the only thing that clears it.
    @Volatile private var liveViewPumpFailedEpoch: Int = -1
    // Set true only for HTTP 503, Sony's known retryable producer state, and
    // reset on every other outcome. Other HTTP responses fail like transport
    // errors instead of burning the producer-restart budget.
    @Volatile private var lastLiveViewHttpRetryableReject = false
    // True from the first detected failure until a replacement stream has
    // been opened. The keepalive watchdog may atomically claim recovery only
    // while false, so it cannot close a channel while the pump is already
    // reopening it or waiting through Sony's HTTP 503 interval.
    private val liveViewRecoveryActive = AtomicBoolean(false)
    @Volatile private var sessionConnectedAtNanos: Long = 0L
    private val eventQueue = LinkedBlockingQueue<ByteArray>()
    @Volatile private var eventThreadRunning = false
    @Volatile private var keepAliveThreadRunning = false
    @Volatile private var liveViewStreaming = false
    @Volatile private var liveViewControlTransition = false
    @Volatile private var liveViewPrimed = false

    @Volatile var isConnected: Boolean = false
        private set
    @Volatile var lastDisconnectReason: String = "never connected"
        private set

    @Volatile var lastCapturedImage: ByteArray? = null
        private set
    @Volatile var lastCapturedFilename: String? = null
        private set
    @Volatile var lastCapturedObjectFormat: Int? = null
        private set
    @Volatile var lastLiveViewDiagnostic: String = "not run"
        private set
    @Volatile private var currentZoomScale: Int = 1_000
    @Volatile private var currentOpticalZoomPercent: Int = 0
    @Volatile private var currentLiveViewStatus: Long? = null
    @Volatile private var currentShootingFileInfo: Long? = null

    data class BurstTestResult(
        val success: Boolean,
        val requestedFrames: Int,
        val holdMs: Long,
        val driveModeApplied: Boolean,
        val objectAddedEvents: Int,
        val eventCodes: List<Int>,
        val retrievedFrames: Int,
        val readyCountPeak: Int,
        val selectedFrameIndex: Int?,
        val sharpnessScores: List<Double>,
        val selectedImage: ByteArray?,
        val restoredSingleShot: Boolean,
        val error: String?
    ) {
        /** Compatibility alias for the existing diagnostic receiver. */
        val latestImage: ByteArray? get() = selectedImage
    }

    data class CardObject(
        val handle: Long,
        val filename: String?,
        val objectFormat: Int?,
        val objectSize: Long?
    )

    data class CardObjectProbe(
        val storageIds: List<Long>,
        val totalHandles: Int,
        val newestObjects: List<CardObject>,
        val error: String?
    )

    private data class BufferedCapture(
        val bytes: ByteArray,
        val filename: String?,
        val objectFormat: Int?
    )

    /**
     * Read-only proof for deferred full-resolution transfer. Lists Sony's
     * normal on-card PTP objects without downloading image payloads. Keep
     * this on the existing authenticated command session: the ZV-E10 II has
     * one remote-control session, while HTTP Live View is only a sibling SSH
     * channel. Opening a second PTP session would steal/kill production.
     */
    fun probeCardObjects(maxNewest: Int = 12): CardObjectProbe =
        withLiveViewHttpReleasedForControl {
            try {
                val storageResult = executeOperation(PTP_OC_GetStorageIDs)
                if (!storageResult.isOk) {
                    return@withLiveViewHttpReleasedForControl CardObjectProbe(
                        emptyList(), 0, emptyList(),
                        "GetStorageIDs response=0x${storageResult.code.toString(16)}"
                    )
                }
                val storageIds = parsePtpU32Array(storageResult.data)
                val handlesResult = executeOperation(
                    PTP_OC_GetObjectHandles,
                    intArrayOf(0xFFFFFFFF.toInt(), 0, 0)
                )
                if (!handlesResult.isOk) {
                    return@withLiveViewHttpReleasedForControl CardObjectProbe(
                        storageIds, 0, emptyList(),
                        "GetObjectHandles response=0x${handlesResult.code.toString(16)}"
                    )
                }
                val handles = parsePtpU32Array(handlesResult.data)
                val newest = handles.takeLast(maxNewest.coerceIn(1, 50)).mapNotNull { unsignedHandle ->
                    val info = executeOperation(PTP_OC_GetObjectInfo, intArrayOf(unsignedHandle.toInt()))
                    if (!info.isOk) return@mapNotNull null
                    CardObject(
                        handle = unsignedHandle,
                        filename = if (info.data.size > 52) {
                            readPtpValue(info.data, 52, 0xFFFF)?.stringValue
                        } else null,
                        objectFormat = if (info.data.size >= 6) info.data.readU16LeAt(4) else null,
                        objectSize = if (info.data.size >= 12) info.data.readU32LeAt(8) else null
                    )
                }
                CardObjectProbe(storageIds, handles.size, newest, null)
            } catch (e: Exception) {
                CardObjectProbe(emptyList(), 0, emptyList(), e.message ?: e.javaClass.simpleName)
            }
        }

    private fun parsePtpU32Array(data: ByteArray): List<Long> {
        if (data.size < 4) return emptyList()
        val count = data.readU32LeAt(0)
        if (count > 1_000_000L || data.size < 4L + count * 4L) return emptyList()
        return List(count.toInt()) { index -> data.readU32LeAt(4 + index * 4) }
    }

    private data class BurstDrainStats(
        val objectAddedEvents: Int,
        val readyCountPeak: Int,
        val shutterHoldMs: Long
    )

    /**
     * Blocking connect -- run this off the main thread. sshUser/sshPassword
     * come from the camera's own MENU -> Network -> Network Option ->
     * Access Authen. Info screen (labeled "User" and "Password" there).
     * Returns true once the full handshake (SSH auth -> tunnel open ->
     * PTP-IP Init Command/Event -> OpenSession -> SDIOConnect x3 phases)
     * has completed successfully.
     */
    fun connectBlocking(
        cameraIp: String,
        sshUser: String,
        sshPassword: String,
        friendlyName: String = "CaptureCam",
        timeoutMs: Int = 8000
    ): Boolean {
        // A previous failed/half-open attempt must never retain Sony's
        // single remote-control slot. This is safe on a fresh controller.
        disconnect()
        transactionId.set(0)
        eventQueue.clear()
        var connected = false
        try {
            val jsch = JSch()
            val session = jsch.getSession(sshUser, cameraIp, 22)
            configureSshSession(session, sshPassword, timeoutMs)
            session.connect(timeoutMs)
            sshSession = session
            // Use a physically separate SSH transport for the high-volume
            // HTTP stream. This gives Live View its own JSch reader and flow-
            // control window instead of merely adding another channel to the
            // PTP session. Some bodies allow only one SSH login; those fall
            // back to the primary transport without failing the camera.
            var dedicatedLiveViewSession = try {
                val liveViewSshTimeoutMs = minOf(timeoutMs, 2_000)
                jsch.getSession(sshUser, cameraIp, 22).also { liveSession ->
                    configureSshSession(liveSession, sshPassword, liveViewSshTimeoutMs)
                    liveSession.connect(liveViewSshTimeoutMs)
                }
            } catch (e: Exception) {
                Log.w(TAG, "Dedicated Sony Live View SSH unavailable; using shared tunnel: ${e.message}")
                null
            }
            liveViewSshSession = dedicatedLiveViewSession
            Log.i(TAG, "SSH authenticated to $cameraIp as $sshUser")
            Log.i(
                TAG,
                "Sony Live View SSH transport=" +
                    (if (dedicatedLiveViewSession != null) "dedicated" else "shared") +
                    " direct-tcpip -> $TUNNEL_HOST:$LIVE_VIEW_REMOTE_PORT"
            )

            val ctrl = openTunnelChannel(session, timeoutMs) ?: run {
                Log.w(TAG, "Failed to open control tunnel channel")
                return false
            }
            controlChannel = ctrl
            controlOut = ctrl.outputStream
            controlIn = ctrl.inputStream

            val guid = uuidToBytes(UUID.randomUUID())
            sendInitCommandRequest(guid, friendlyName)
            val connId = readInitCommandAck() ?: run {
                Log.w(TAG, "No/bad Init Command Ack")
                return false
            }
            Log.i(TAG, "Init Command Ack received, connId=$connId")

            val evt = openTunnelChannel(session, timeoutMs) ?: run {
                Log.w(TAG, "Failed to open event tunnel channel")
                return false
            }
            eventChannel = evt
            eventOut = evt.outputStream
            eventIn = evt.inputStream
            sendInitEventRequest(eventOut!!, connId)
            val eventAckType = readPacketType(eventIn!!)
            if (eventAckType != PKT_INIT_EVENT_ACK) {
                Log.w(TAG, "Expected Init Event Ack, got type $eventAckType")
                return false
            }

            startEventReaderThread()

            if (!operationNoData(PTP_OC_OpenSession, intArrayOf(1))) {
                Log.w(TAG, "OpenSession failed")
                return false
            }
            if (!operationNoData(PTP_OC_GetDeviceInfo, intArrayOf())) {
                Log.w(TAG, "GetDeviceInfo failed")
                return false
            }
            if (!operationNoData(PTP_OC_GetStorageIDs, intArrayOf())) {
                Log.w(TAG, "GetStorageIDs failed")
                return false
            }

            // Sony SDIO 3-phase handshake -- confirmed sequence against
            // alpha-fairy's real-device-tested init_table (see class doc).
            if (!operationNoData(OC_SDIOConnect, intArrayOf(1, 0, 0))) {
                Log.w(TAG, "SDIOConnect phase 1 failed"); return false
            }
            if (!operationNoData(OC_SDIOConnect, intArrayOf(2, 0, 0))) {
                Log.w(TAG, "SDIOConnect phase 2 failed"); return false
            }
            // Vendor v310 cameras advertise the option-flag form through a
            // dedicated query (Creators' SDIO_GetVendorCodeVersion, 0x9216).
            // The legacy [300,0,0] ExtDeviceInfo request returned data but
            // initialized the command layer without the required option flag.
            val vendorVersionResult = executeOperation(
                OC_SDIOGetVendorCodeVersion,
                intArrayOf()
            )
            if (!vendorVersionResult.isOk || vendorVersionResult.params.isEmpty()) {
                Log.w(TAG, "Sony vendor-code-version query failed"); return false
            }
            sdiVendorCodeVersion = vendorVersionResult.params.first()
            val extInfoParams = if (usesDevicePropertyOption()) {
                intArrayOf(SDI_VERSION_V3, 1)
            } else {
                intArrayOf(SDI_VERSION_V3)
            }
            val phase2ExtInfo = executeOperation(OC_SDIOGetExtDeviceInfo, extInfoParams)
            if (!phase2ExtInfo.isOk) {
                Log.w(TAG, "SDIO extended device info after phase 2 failed"); return false
            }

            // Authentication must be complete before property/mode writes.
            // Sony's reference implementation performs phase 3 here. The
            // previous ordering wrote D25A/5013 before phase 3; Sony ACKed
            // those packets but did not arm the shutter physically.
            if (!operationNoData(OC_SDIOConnect, intArrayOf(3, 0, 0))) {
                Log.w(TAG, "SDIOConnect phase 3 failed"); return false
            }
            Log.i(
                TAG,
                "Sony SDI vendor code version=$sdiVendorCodeVersion " +
                    "devicePropertyOption=${if (usesDevicePropertyOption()) 1 else 0}"
            )

            // Populate Sony property state after authentication.
            var propertyBootstrap = readSonyProperties()
            Log.i(TAG, "Sony property bootstrap parsed ${propertyBootstrap.size} properties")
            // Capability audit (2026-08-30): the body advertises ~366 device
            // properties while this app defines 33. Log which of the
            // advertised ones are WRITABLE and currently ENABLED, so unused
            // camera capability can be identified from the camera's own
            // report rather than guessed at. Writable+enabled is the subset
            // that could actually be driven right now.
            val actionable = propertyBootstrap.values
                .filter { it.writable && it.enabled }
                .map { it.code }
                .sorted()
            Log.i(
                TAG,
                "Sony capability audit: writable+enabled=${actionable.size}/${propertyBootstrap.size} " +
                    "codes=" + actionable.joinToString(",") { "0x%04X".format(it) }
            )
            if (propertyBootstrap.isEmpty()) return false
            currentZoomScale = propertyBootstrap[PROP_ZoomScale]?.currentValue?.toInt() ?: 1_000
            currentOpticalZoomPercent = opticalZoomPercent(
                propertyBootstrap[PROP_ZoomOptical]?.currentValue
            ) ?: 0
            liveViewUrl = propertyBootstrap[PROP_LiveViewUrl]?.currentString
            if (liveViewUrl.isNullOrBlank()) {
                Log.w(TAG, "Sony LiveViewURL property 0xD278 was empty")
            } else {
                Log.i(TAG, "Sony LiveViewURL discovered: $liveViewUrl")
            }

            // The body defaults unpredictably between image-quality and
            // display-speed live view. In image-quality mode the observed
            // 60-176 KB JPEGs make source FPS track scene complexity and
            // fall to 6-10 FPS. Sony's documented PTP value 0x01 requests
            // display-speed priority. This must happen after the 0x9209
            // bootstrap but before the HTTP stream is opened, matching the
            // Creators' App ordering.
            val liveViewQuality = propertyBootstrap[PROP_LiveViewQuality]
            Log.i(
                TAG,
                "Sony Live View quality 0xD26A current=${liveViewQuality?.currentValue} " +
                    "enabled=${liveViewQuality?.enabled} writable=${liveViewQuality?.writable} " +
                    "type=0x${liveViewQuality?.dataType?.toString(16)} " +
                    "values=${liveViewQuality?.supportedValues}"
            )
            val displaySpeedSet = setControlDeviceARaw(
                PROP_LiveViewQuality,
                byteArrayOf(LIVE_VIEW_QUALITY_DISPLAY_SPEED.toByte())
            )
            Log.i(TAG, "Sony Live View display-speed priority set result: $displaySpeedSet")

            // Creators' App uses RemoteTouchOperation for focus at an exact
            // Live View coordinate. This body boots with touch OFF (D283=1),
            // which leaves D284 disabled. Its advertised modes include 9 =
            // Touch Focus + Touch AE OFF: ideal here because CaptureCam owns
            // exposure independently and must focus only on detected gold.
            val touchMode = propertyBootstrap[PROP_FunctionOfTouchOperation]
            if (touchMode?.writable == true && touchMode.supportedValues.contains(9L)) {
                val touchModeSet = setControlDeviceARaw(
                    PROP_FunctionOfTouchOperation,
                    byteArrayOf(9)
                )
                Log.i(TAG, "Sony touch-focus mode set result: $touchModeSet")
                if (touchModeSet) {
                    // The write ACK precedes the property change by roughly
                    // one update cycle on this body. Wait for D283=9 before
                    // evaluating D284 or we cache the old disabled state.
                    waitForPropertyValue(
                        PROP_FunctionOfTouchOperation,
                        9L,
                        1_000L
                    )
                    propertyBootstrap = readSonyProperties()
                }
            }
            val remoteTouch = propertyBootstrap[PROP_RemoteTouchOperationEnable]
            remoteTouchFocusEnabled = remoteTouch?.enabled == true && remoteTouch.currentValue == 1L
            Log.i(
                TAG,
                "Sony remote touch focus enabled=$remoteTouchFocusEnabled " +
                    "mode=${propertyBootstrap[PROP_FunctionOfTouchOperation]?.currentValue} " +
                    "control=${remoteTouch?.currentValue}/${remoteTouch?.enabled}"
            )

            // D25A is Sony's Position Key: value 1 hands control to the
            // remote host. Then 5013=1 selects single-shot drive mode.
            if (!setControlDeviceARaw(PROP_PositionKey, byteArrayOf(1))) {
                Log.w(TAG, "Failed to enable Sony remote Position Key"); return false
            }
            // Confirmed on ZV-E10 II, every reconnect: 5013 (OperatingMode)
            // NEVER reports IsEnable=true, even after Position Key becomes
            // 1, while D221 reports active Live View regardless -- this is
            // valid, expected state for this body (other Sony models, e.g.
            // RX100 VII, expose it normally -- do not "fix" this for those).
            // waitForPropertyEnabled(..., 1_000L) therefore ALWAYS burned
            // its full 1-second budget polling for something proven to
            // never happen here -- the single largest cost in the whole
            // reconnect sequence. Skipping it directly cuts ~1s off every
            // reconnect (measured baseline was ~1.4-1.6s total).
            val operatingModeExposed = false
            val stillMode = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN)
                .putInt(DRIVE_SINGLE).array()
            if (!setControlDeviceARaw(PROP_DriveMode, stillMode)) {
                Log.w(TAG, "Failed to enter Sony still-ready mode"); return false
            }
            if (operatingModeExposed &&
                !waitForPropertyValue(PROP_DriveMode, DRIVE_SINGLE.toLong(), 5_000L)) {
                Log.w(TAG, "Sony still-ready mode was not confirmed"); return false
            }

            // Request both a host object (for CaptureCam) and an on-card copy.
            val saveMedia = ByteBuffer.allocate(2).order(ByteOrder.LITTLE_ENDIAN)
                .putShort(SAVE_MEDIA_HOST_AND_CAMERA.toShort()).array()
            if (!setControlDeviceARaw(PROP_SaveMedia, saveMedia)) {
                Log.w(TAG, "Failed to set Sony save-media destination"); return false
            }
            if (!waitForPropertyValue(PROP_SaveMedia, SAVE_MEDIA_HOST_AND_CAMERA.toLong(), 5_000L)) {
                Log.w(TAG, "Sony save-media destination was not confirmed"); return false
            }

            isConnected = true
            lastDisconnectReason = "none"
            connected = true
            sessionConnectedAtNanos = System.nanoTime()
            liveViewPumpFailedEpoch = -1
            liveViewRecoveryActive.set(false)

            // Full-time autofocus: set the camera's OWN AF-C (continuous AF)
            // hardware mode once here, rather than repeatedly triggering S1
            // from the app -- repeated triggering would go through
            // runFreshControl()'s session-teardown path (see driveAutoFocus
            // call sites), which would be exactly the kind of constant
            // disruption we just fixed for the natural 45s cycle. AF-C mode
            // itself is confirmed reachable through the serialized property
            // setter. The live 0x9209 table reports 0x500A writable and AF-C
            // (0x8004) as a supported value.
            // Tested live 2026-08-24: disabling this did NOT restore the
            // ~25fps baseline (still measured 6.3-8.4fps with it off) -- AF-C
            // is not the cause of the fps regression. Re-enabled.
            val afcResult = setFocusMode(AFMODE_AFC)
            Log.i(TAG, "Sony AF-C (full-time autofocus) set result: $afcResult")

            startKeepAliveThread()
            Log.i(TAG, "Sony PTP-IP-over-SSH handshake complete")
            return true
        } catch (e: Exception) {
            Log.w(TAG, "Connect failed: ${e.message}", e)
            return false
        } finally {
            // Kotlin executes this for every early `return false` above.
            // Without it, a failed SDIO phase left SSH/tunnel channels open
            // and Sony rejected the next attempt until its own long timeout.
            if (!connected) disconnect()
        }
    }

    private fun openTunnelChannel(
        session: Session,
        timeoutMs: Int,
        destinationPort: Int = TUNNEL_PORT
    ): ChannelDirectTCPIP? {
        return try {
            val channel = session.openChannel("direct-tcpip") as ChannelDirectTCPIP
            channel.setHost(TUNNEL_HOST)
            channel.setPort(destinationPort)
            tuneTunnelChannelWindow(channel, SSH_CONTROL_WINDOW_BYTES)
            channel.connect(timeoutMs)
            channel
        } catch (e: Exception) {
            Log.w(TAG, "openTunnelChannel($TUNNEL_HOST:$destinationPort) failed: ${e.message}")
            null
        }
    }

    private fun configureSshSession(session: Session, password: String, timeoutMs: Int) {
        session.setPassword(password)
        // Trust-on-first-use on the operator-controlled camera LAN.
        session.setConfig("StrictHostKeyChecking", "no")
        // Keep enough receive-pipe headroom for both the 25fps preview and
        // 15-20MB original JPEG transfers. The previous 1MB pipe still made
        // a full-resolution GetObject repeatedly stop for WINDOW_ADJUST;
        // measured live: a 17.9MB original spent 7.0s in download alone.
        session.setConfig("max_input_buffer_size", SSH_CONTROL_WINDOW_BYTES.toString())
        session.setConfig(
            "cipher.s2c",
            "aes128-ctr,aes192-ctr,aes256-ctr,aes128-cbc,aes192-cbc,aes256-cbc,3des-ctr,3des-cbc"
        )
        session.setConfig(
            "cipher.c2s",
            "aes128-ctr,aes192-ctr,aes256-ctr,aes128-cbc,aes192-cbc,aes256-cbc,3des-ctr,3des-cbc"
        )
        session.setConfig("compression.s2c", "none")
        session.setConfig("compression.c2s", "none")
        session.timeout = timeoutMs
        session.serverAliveInterval = 10_000
        session.serverAliveCountMax = 3
    }

    fun disconnect(reason: String = "requested") {
        lastDisconnectReason = reason
        connectionEpoch.incrementAndGet()
        isConnected = false
        eventThreadRunning = false
        keepAliveThreadRunning = false
        // Keep liveViewStreaming true until every transport is closed. A
        // keepalive thread that passed its loop guard just before this call
        // will then skip its PTP request instead of racing one into Sony's
        // single command slot while a replacement session is opening.
        //
        // Stop the pump before tearing down SSH: its reader thread may be
        // parked in a blocking read, and stopLiveViewPump() disconnects the
        // channel from outside the read lock specifically so that read can
        // be cancelled rather than wedging shutdown.
        liveViewPumpRunning = false
        liveViewRecoveryActive.set(false)
        forceCloseLiveViewChannel()
        synchronized(liveViewSampleMonitor) { liveViewSampleMonitor.notifyAll() }
        liveViewPumpThread = null
        latestLiveViewSample.set(null)
        lastServedSequence = 0L
        closeLiveViewHttpStream()
        try { controlChannel?.disconnect() } catch (_: Exception) {}
        try { eventChannel?.disconnect() } catch (_: Exception) {}
        try { liveViewSshSession?.disconnect() } catch (_: Exception) {}
        try { sshSession?.disconnect() } catch (_: Exception) {}
        liveViewStreaming = false
        liveViewPrimed = false
        sshSession = null; liveViewSshSession = null; controlChannel = null; eventChannel = null
        controlIn = null; controlOut = null; eventIn = null; eventOut = null
        liveViewUrl = null
        sdiVendorCodeVersion = 0
        remoteTouchFocusEnabled = false
    }

    // ---- High-level camera actions -------------------------------------

    fun triggerShutter(
        afSettleMs: Long = 250L,
        holdMs: Long = 120L,
        onShotReady: (() -> Unit)? = null
    ): Boolean {
        val captureStartedAt = System.currentTimeMillis()
        lastCapturedImage = null
        lastCapturedFilename = null
        lastCapturedObjectFormat = null
        if (currentLiveViewStatus != 1L &&
            !waitForPropertyValue(PROP_LiveViewStatus, 1L, 10_000L)) {
            Log.w(TAG, "Shutter blocked: Sony Live View did not become ready")
            return false
        }

        // D215's host object is a FIFO entry, not a busy bit that clears by
        // itself. The old code waited ten seconds for a stale object to
        // disappear even though only GetObject can pop it. Consume any stale
        // object now so it can never be mistaken for this shutter's result.
        val staleState = readSonyProperties()[PROP_ShootingFileInfo]?.currentValue ?: 0L
        if (sonyBufferedCaptureCount(staleState) > 0) {
            val discarded = mutableListOf<BufferedCapture>()
            val discardStartedAt = System.currentTimeMillis()
            if (!popSonyHostCapture(discarded)) {
                Log.w(TAG, "Shutter blocked: stale Sony host object could not be drained")
                return false
            }
            Log.w(
                TAG,
                "Discarded stale Sony host object before shutter bytes=${discarded.first().bytes.size} " +
                    "elapsedMs=${System.currentTimeMillis() - discardStartedAt}"
            )
        }

        eventQueue.clear()
        var shutterPressedAt = 0L
        var objectReadyAt = 0L
        val shotReady = synchronized(operationLock) {
            var autofocusHeld = false
            var captureHeld = false
            try {
                // AF-C already tracks continuously. A short acknowledged S1
                // pulse lets the body confirm the final focus position; a
                // 1.5s S1 delay plus two 1.5s S2 sleeps added 4.5 artificial
                // seconds to every still without improving a static subject.
                if (!setControlDeviceB(PROP_AutoFocus, 2, 2)) return@synchronized false
                autofocusHeld = true
                Thread.sleep(afSettleMs)
                if (!setControlDeviceB(PROP_Capture, 2, 2)) return@synchronized false
                captureHeld = true
                shutterPressedAt = System.currentTimeMillis()
                Thread.sleep(holdMs)
                waitForShootingFileReadyEventFirst(30_000L).also { ready ->
                    if (ready) objectReadyAt = System.currentTimeMillis()
                }
            } catch (e: Exception) {
                Log.w(TAG, "Sony shutter control sequence write failed: ${e.message}", e)
                false
            } finally {
                // Sony's virtual S2 must remain held until the body completes
                // the exposure. A fixed 120ms release ACKed but cancelled the
                // actual still on the live ZV-E10 II. Always release S2/S1,
                // including failure/timeout paths, so no virtual key sticks.
                if (captureHeld) setControlDeviceB(PROP_Capture, 1, 2)
                if (autofocusHeld) setControlDeviceB(PROP_AutoFocus, 1, 2)
            }
        }
        val shutterReleasedAt = System.currentTimeMillis()
        if (!shotReady) {
            Log.w(TAG, "Shutter sequence ACKed, but no Sony shot object became ready")
            return false
        }
        // Exposure is complete and Sony's host object exists. The heavy
        // original download still follows, but UI/gimbal work can start now.
        onShotReady?.invoke()

        val infoStartedAt = System.currentTimeMillis()
        val info = executeOperation(PTP_OC_GetObjectInfo, intArrayOf(SHOT_OBJECT_HANDLE))
        if (!info.isOk) return false
        val infoCompletedAt = System.currentTimeMillis()
        val objectFormat = if (info.data.size >= 6) info.data.readU16LeAt(4) else null
        val objectSize = if (info.data.size >= 12) info.data.readU32LeAt(8) else null
        val pixelWidth = if (info.data.size >= 30) info.data.readU32LeAt(26) else null
        val pixelHeight = if (info.data.size >= 34) info.data.readU32LeAt(30) else null
        val fileName = if (info.data.size > 52) {
            readPtpValue(info.data, 52, 0xFFFF)?.stringValue
        } else null
        val downloadStartedAt = System.currentTimeMillis()
        val shot = executeOperation(PTP_OC_GetObject, intArrayOf(SHOT_OBJECT_HANDLE))
        if (!shot.isOk || shot.data.isEmpty()) return false
        val downloadCompletedAt = System.currentTimeMillis()
        lastCapturedImage = shot.data
        lastCapturedFilename = fileName
        lastCapturedObjectFormat = objectFormat
        val payloadType = when {
            shot.data.size >= 2 && shot.data[0] == 0xFF.toByte() && shot.data[1] == 0xD8.toByte() -> "JPEG"
            shot.data.size >= 4 && shot.data[0] == 'I'.code.toByte() && shot.data[1] == 'I'.code.toByte() &&
                shot.data[2] == 0x2A.toByte() && shot.data[3] == 0x00.toByte() -> "TIFF/ARW"
            else -> "unknown"
        }
        Log.i(
            TAG,
            "Sony still captured and downloaded: ${shot.data.size}B payload=$payloadType " +
                "filename=$fileName format=${objectFormat?.let { "0x${it.toString(16)}" }} " +
                "declaredSize=$objectSize dimensions=${pixelWidth}x$pixelHeight " +
                "timingMs={preShutter=${shutterPressedAt - captureStartedAt}," +
                "camera=${objectReadyAt - shutterPressedAt}," +
                "release=${shutterReleasedAt - objectReadyAt}," +
                "info=${infoCompletedAt - infoStartedAt}," +
                "download=${downloadCompletedAt - downloadStartedAt}," +
                "total=${downloadCompletedAt - captureStartedAt}}"
        )
        return true
    }

    /**
     * Captures a native Hi+ burst, drains every Sony host-buffer object, scores
     * the first [frameCount] full-resolution images without altering their
     * bytes, and exposes the sharpest original through [lastCapturedImage].
     *
     * Sony does not assign a distinct host handle to each frame. D215 contains
     * 0x8000 | queuedCount and every GetObject(0xFFFFC001) pops one frame from
     * that FIFO. C201/0xFFFFC001 is only a wake-up hint; D215 is authoritative.
     */
    fun triggerBurstTest(frameCount: Int = 5): BurstTestResult {
        val requested = frameCount.coerceIn(2, 10)
        var holdMs = 0L
        var driveApplied = false
        var restoredSingle = false
        var error: String? = null
        val eventCodes = mutableListOf<Int>()
        var objectAddedEvents = 0
        var readyCountPeak = 0
        val captured = mutableListOf<BufferedCapture>()
        var selectedFrameIndex: Int? = null
        var selectedImage: ByteArray? = null
        var sharpnessScores = emptyList<Double>()

        try {
            // A failed/aborted earlier capture can survive in Sony host RAM.
            // Drain it before firing so an old file can never win this burst.
            val stale = drainSonyHostCaptureQueue(
                captures = null,
                maxFrames = 10,
                timeoutMs = 5_000L,
                stopWhenQuiet = true
            )
            if (stale > 0) Log.w(TAG, "Discarded $stale stale Sony host capture(s) before burst")

            val drive = readSonyProperties()[PROP_DriveMode]
            if (drive == null || !drive.supportedValues.contains(DRIVE_CONTINUOUS_HI_PLUS.toLong())) {
                error = "Continuous Hi+ is not advertised by this camera state"
            } else {
                driveApplied = setControlDeviceASerialized(PROP_DriveMode, DRIVE_CONTINUOUS_HI_PLUS, 4) &&
                    waitForPropertyValue(PROP_DriveMode, DRIVE_CONTINUOUS_HI_PLUS.toLong(), 3_000L)
                if (!driveApplied) error = "Continuous Hi+ write/readback failed"
            }

            if (error == null) {
                eventQueue.clear()
                var autofocusHeld = false
                var shutterHeld = false
                try {
                    if (!setControlDeviceB(PROP_AutoFocus, 2, 2)) {
                        error = "S1 press failed"
                    } else {
                        autofocusHeld = true
                        Thread.sleep(250L)
                    }
                    if (error == null) {
                        if (!setControlDeviceB(PROP_Capture, 2, 2)) {
                            error = "S2 press failed"
                        } else {
                            shutterHeld = true
                            // Keep S2 held while each 0xFFFFC001 object is
                            // downloaded. Sony exposes one host slot at a time;
                            // releasing first leaves only one candidate.
                            val stats = captureBurstWhileShutterHeld(
                                requested = requested,
                                captures = captured,
                                eventCodes = eventCodes,
                                timeoutMs = 45_000L
                            )
                            objectAddedEvents = stats.objectAddedEvents
                            readyCountPeak = stats.readyCountPeak
                            holdMs = stats.shutterHoldMs
                            if (!setControlDeviceB(PROP_Capture, 1, 2)) {
                                error = "S2 release was not acknowledged"
                            } else {
                                shutterHeld = false
                            }
                        }
                    }
                } catch (e: Exception) {
                    error = "Burst control failed: ${e.message}"
                } finally {
                    // A Sony virtual shutter has no timeout. Never leave S2/S1
                    // logically held, even if the test throws mid-sequence.
                    if (shutterHeld) {
                        try { setControlDeviceB(PROP_Capture, 1, 2) } catch (_: Exception) { }
                    }
                    if (autofocusHeld) {
                        try { setControlDeviceB(PROP_AutoFocus, 1, 2) } catch (_: Exception) { }
                    }
                }

                objectAddedEvents += collectBurstEvents(eventCodes, 500L)
                if (captured.size < requested) {
                    error = "Sony burst incomplete: retrieved ${captured.size}/$requested host frames"
                } else {
                    // Ignore any timing-boundary surplus for best-of-N scoring,
                    // but still drain it from camera RAM above.
                    val candidates = captured.take(requested)
                    sharpnessScores = candidates.map { sharpnessScore(it.bytes) }
                    selectedFrameIndex = sharpnessScores.indices.maxByOrNull { sharpnessScores[it] }
                    selectedImage = selectedFrameIndex?.let { candidates[it].bytes }
                    val selected = selectedFrameIndex?.let { candidates[it] }
                    if (selectedImage == null || sharpnessScores.all { !it.isFinite() }) {
                        error = "No decodable burst frame available for sharpness scoring"
                    } else {
                        lastCapturedImage = selectedImage
                        lastCapturedFilename = selected?.filename
                        lastCapturedObjectFormat = selected?.objectFormat
                    }
                }
            }
        } catch (e: Exception) {
            error = error ?: "Burst test failed: ${e.message}"
        } finally {
            try {
                val restoreAck = setControlDeviceASerialized(PROP_DriveMode, DRIVE_SINGLE, 4)
                // Sony can return a late/negative command ACK while its card
                // writer is draining even though the setting was applied.
                // The property readback is the hardwall, not the ACK bit.
                restoredSingle = waitForPropertyValue(
                    PROP_DriveMode,
                    DRIVE_SINGLE.toLong(),
                    1_000L
                )
                if (!restoreAck && restoredSingle) {
                    Log.w(TAG, "Sony single-shot restore ACK was false; readback confirmed mode=1")
                }
                if (!restoredSingle) {
                    error = error ?: "Single-shot restore readback failed"
                }
            } catch (e: Exception) {
                error = error ?: "Single-shot restore failed: ${e.message}"
            }
        }

        val success = error == null && driveApplied && restoredSingle &&
            captured.size >= requested && selectedImage != null
        Log.i(
            TAG,
            "Sony burst test success=$success requested=$requested holdMs=$holdMs " +
                "driveApplied=$driveApplied objectAdded=$objectAddedEvents " +
                "events=${eventCodes.map { "0x${it.toString(16)}" }} " +
                "retrieved=${captured.size} readyPeak=$readyCountPeak " +
                "selected=$selectedFrameIndex scores=${sharpnessScores.map { "%.1f".format(it) }} " +
                "selectedBytes=${selectedImage?.size} restoredSingle=$restoredSingle error=$error"
        )
        return BurstTestResult(
            success, requested, holdMs, driveApplied, objectAddedEvents,
            eventCodes, captured.size, readyCountPeak, selectedFrameIndex,
            sharpnessScores, selectedImage, restoredSingle, error
        )
    }

    /**
     * Captures/scans the same native burst using Sony's 2M host-transfer
     * resource. Full RAW+JPEG files remain on the memory card because the
     * save destination stays Host+Camera. Restores the operator's transfer
     * size before returning, even on failure.
     */
    fun triggerProxyBurstTest(frameCount: Int = 5): BurstTestResult {
        val before = readSonyProperties()[PROP_StillImageTransferSize]?.currentValue?.toInt()
            ?: TRANSFER_SIZE_ORIGINAL
        val proxySet = setStillImageTransferSize(TRANSFER_SIZE_2M) &&
            waitForPropertyValue(
                PROP_StillImageTransferSize,
                TRANSFER_SIZE_2M.toLong(),
                3_000L
            )
        if (!proxySet) {
            return BurstTestResult(
                success = false,
                requestedFrames = frameCount.coerceIn(2, 10),
                holdMs = 0L,
                driveModeApplied = false,
                objectAddedEvents = 0,
                eventCodes = emptyList(),
                retrievedFrames = 0,
                readyCountPeak = 0,
                selectedFrameIndex = null,
                sharpnessScores = emptyList(),
                selectedImage = null,
                restoredSingleShot = true,
                error = "Sony 2M proxy transfer-size write/readback failed"
            )
        }
        return try {
            triggerBurstTest(frameCount)
        } finally {
            val restored = setStillImageTransferSize(before) &&
                waitForPropertyValue(PROP_StillImageTransferSize, before.toLong(), 3_000L)
            if (!restored) {
                Log.e(TAG, "Sony transfer-size restore failed expected=$before")
            }
        }
    }

    /**
     * Sony host transfer is a one-slot FIFO on this body. Keep S2 logically
     * down and pop one virtual object whenever D215 becomes ready. That lets
     * the body advance to the next exposure without guessing shutter speed.
     */
    private fun captureBurstWhileShutterHeld(
        requested: Int,
        captures: MutableList<BufferedCapture>,
        eventCodes: MutableList<Int>,
        timeoutMs: Long
    ): BurstDrainStats {
        val started = System.currentTimeMillis()
        val deadline = System.currentTimeMillis() + timeoutMs
        var sonyObjectAdded = 0
        var readyPeak = 0
        var lastPropertyFallbackAt = 0L
        while (hasOpenControlTransport() && captures.size < requested &&
            System.currentTimeMillis() < deadline) {
            // C201 is Sony's exact "host object ready" notification. The old
            // loop hammered the 9.6KB 0x9209 property dataset every 50ms,
            // serializing 100+ commands with card writing and stretching a
            // 190KB proxy burst to 11 seconds. Let the event channel wake the
            // downloader; keep D215 only as a low-rate lost-event fallback.
            val added = collectBurstEvents(eventCodes, 250L)
            sonyObjectAdded += added
            if (added > 0) {
                repeat(added.coerceAtMost(requested - captures.size)) {
                    if (popSonyHostCapture(captures)) readyPeak = maxOf(readyPeak, 1)
                }
                continue
            }
            val now = System.currentTimeMillis()
            if (now - lastPropertyFallbackAt >= 500L) {
                lastPropertyFallbackAt = now
                val value = readSonyProperties()[PROP_ShootingFileInfo]?.currentValue ?: 0L
                val queued = sonyBufferedCaptureCount(value)
                readyPeak = maxOf(readyPeak, queued)
                if (queued > 0) popSonyHostCapture(captures)
            }
        }
        sonyObjectAdded += collectBurstEvents(eventCodes, 0L)
        return BurstDrainStats(
            sonyObjectAdded,
            readyPeak,
            System.currentTimeMillis() - started
        )
    }

    /** Drains raw Sony event packets and returns ObjectAdded count. */
    private fun collectBurstEvents(eventCodes: MutableList<Int>, waitMs: Long): Int {
        var objectAdded = 0
        val first = if (waitMs > 0L) eventQueue.poll(waitMs, TimeUnit.MILLISECONDS) else eventQueue.poll()
        var event = first
        while (event != null) {
            if (event.size >= 2) {
                val code = event.readU16LeAt(0)
                eventCodes += code
                if (code == PTP_EC_ObjectAdded || code == PTP_EC_SonyObjectAdded) {
                    objectAdded += 1
                    val handle = if (event.size >= 10) event.readU32LeAt(6) else null
                    Log.d(TAG, "Sony burst ObjectAdded event=0x${code.toString(16)} handle=${handle?.let { "0x${it.toString(16)}" }}")
                }
            }
            event = eventQueue.poll()
        }
        return objectAdded
    }

    /**
     * Pops Sony's 0xFFFFC001 FIFO until D215 is empty or [maxFrames] is hit.
     * Returns the number of successfully removed objects. When [captures] is
     * null the objects are deliberately discarded as stale pre-burst data.
     */
    private fun drainSonyHostCaptureQueue(
        captures: MutableList<BufferedCapture>?,
        maxFrames: Int,
        timeoutMs: Long,
        stopWhenQuiet: Boolean
    ): Int {
        val deadline = System.currentTimeMillis() + timeoutMs
        var drained = 0
        while (hasOpenControlTransport() && drained < maxFrames && System.currentTimeMillis() < deadline) {
            val state = readSonyProperties()[PROP_ShootingFileInfo]?.currentValue ?: 0L
            if (sonyBufferedCaptureCount(state) <= 0) {
                if (stopWhenQuiet || drained > 0) break
                Thread.sleep(40L)
                continue
            }
            val target = captures ?: mutableListOf()
            if (!popSonyHostCapture(target)) {
                Thread.sleep(50L)
                continue
            }
            drained += 1
        }
        return drained
    }

    /** Pops exactly one ready object from Sony's virtual host FIFO. */
    private fun popSonyHostCapture(captures: MutableList<BufferedCapture>): Boolean {
        val info = executeOperation(PTP_OC_GetObjectInfo, intArrayOf(SHOT_OBJECT_HANDLE))
        if (!info.isOk) return false
        val objectFormat = if (info.data.size >= 6) info.data.readU16LeAt(4) else null
        val declaredSize = if (info.data.size >= 12) info.data.readU32LeAt(8) else null
        val filename = if (info.data.size > 52) {
            readPtpValue(info.data, 52, 0xFFFF)?.stringValue
        } else null
        val shot = executeOperation(PTP_OC_GetObject, intArrayOf(SHOT_OBJECT_HANDLE))
        if (!shot.isOk || shot.data.isEmpty()) return false
        if (declaredSize != null && declaredSize != 0L && declaredSize != shot.data.size.toLong()) {
            Log.w(TAG, "Sony burst frame size mismatch declared=$declaredSize actual=${shot.data.size}")
        }
        captures.add(BufferedCapture(shot.data, filename, objectFormat))
        Log.i(TAG, "Sony burst frame ${captures.size} downloaded ${shot.data.size}B filename=$filename")
        return true
    }

    private fun sonyBufferedCaptureCount(value: Long): Int {
        if (value and 0x8000L == 0L) return 0
        return (value and 0x7FFFL).toInt()
    }

    /** Variance-of-Laplacian on a downsampled image. Original bytes are kept. */
    private fun sharpnessScore(original: ByteArray): Double {
        val jpeg = if (original.size >= 2 && original[0] == 0xFF.toByte() &&
            original[1] == 0xD8.toByte()) original else extractJpeg(original) ?: return Double.NEGATIVE_INFINITY
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size, bounds)
        if (bounds.outWidth < 3 || bounds.outHeight < 3) return Double.NEGATIVE_INFINITY
        var sample = 1
        while (maxOf(bounds.outWidth, bounds.outHeight) / sample > 960) sample *= 2
        val options = BitmapFactory.Options().apply {
            inSampleSize = sample
            inPreferredConfig = android.graphics.Bitmap.Config.ARGB_8888
        }
        val bitmap = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size, options)
            ?: return Double.NEGATIVE_INFINITY
        return try {
            val width = bitmap.width
            val height = bitmap.height
            if (width < 3 || height < 3) return Double.NEGATIVE_INFINITY
            val pixels = IntArray(width * height)
            bitmap.getPixels(pixels, 0, width, 0, 0, width, height)
            val left = (width * 0.08).toInt().coerceAtLeast(1)
            val right = (width * 0.92).toInt().coerceAtMost(width - 1)
            val top = (height * 0.08).toInt().coerceAtLeast(1)
            val bottom = (height * 0.92).toInt().coerceAtMost(height - 1)
            fun gray(pixel: Int): Int {
                val r = pixel shr 16 and 0xFF
                val g = pixel shr 8 and 0xFF
                val b = pixel and 0xFF
                return (77 * r + 150 * g + 29 * b) shr 8
            }
            var sum = 0.0
            var sumSquares = 0.0
            var count = 0L
            for (y in top until bottom) {
                val row = y * width
                for (x in left until right) {
                    val i = row + x
                    val laplacian = 4 * gray(pixels[i]) - gray(pixels[i - 1]) -
                        gray(pixels[i + 1]) - gray(pixels[i - width]) - gray(pixels[i + width])
                    val value = laplacian.toDouble()
                    sum += value
                    sumSquares += value * value
                    count += 1
                }
            }
            if (count == 0L) Double.NEGATIVE_INFINITY else {
                val mean = sum / count
                (sumSquares / count) - mean * mean
            }
        } finally {
            bitmap.recycle()
        }
    }

    fun driveZoom(tele: Boolean, durationMs: Long): Boolean {
        if (!isConnected) return false
        // Full 16-50mm travel is measured at ~1,650ms. The former 1,500ms
        // ceiling made an endpoint command stop roughly 9% short, so the
        // next tag started visibly zoomed-in after a completed item. Allow
        // a small endpoint overrun; Sony's power-zoom motor safely stops at
        // its own mechanical/electronic limit.
        val holdMs = durationMs.coerceIn(80L, 1_800L)
        val direction = if (tele) ZOOM_TELE_STEP else ZOOM_WIDE_STEP
        val directionName = if (tele) "tele" else "wide"
        val before = currentOpticalZoomPercent.coerceIn(0, 100)
        var pressed = false
        var released = false
        var interrupted = false

        // Match Creators' App: synchronous ZoomOperation Plus/Minus, then
        // Stop, over the PTP command lane while the sibling HTTP downloader
        // keeps draining. Closing HTTP for the whole motor pulse guaranteed
        // a visible preview freeze exactly as long as every zoom action.
        pressed = setControlDeviceB(PROP_ZoomStep, direction, 1)
        if (pressed) {
            try {
                Thread.sleep(holdMs)
            } catch (_: InterruptedException) {
                interrupted = true
            } finally {
                released = setControlDeviceB(PROP_ZoomStep, 0, 1)
            }
        }
        if (interrupted) Thread.currentThread().interrupt()

        val moved = pressed && released
        if (moved) {
            val deltaPercent = (holdMs.toFloat() / PRODUCTION_ZOOM_FULL_TRAVEL_MS * 100f)
                .toInt().coerceAtLeast(1)
            currentOpticalZoomPercent = (before + if (tele) deltaPercent else -deltaPercent)
                .coerceIn(0, 100)
            currentZoomScale = 1_000 + currentOpticalZoomPercent * 10
        }
        Log.i(
            TAG,
            "Sony ZoomOperation direction=$directionName " +
                "holdMs=$holdMs before=${before}% after=${currentOpticalZoomPercent}% " +
                "pressed=$pressed released=$released"
        )
        return moved
    }

    /** Uses non-disruptive remote touch focus. S1 is intentionally not used:
     * this ZV-E10 II stops its HTTP producer after live S1 commands. */
    @Suppress("UNUSED_PARAMETER")
    fun driveAutoFocus(holdMs: Long = 450L): Boolean {
        if (!isConnected) return false
        if (remoteTouchFocusEnabled) return driveTouchFocus(0.5f, 0.5f)
        Log.w(TAG, "Sony remote touch focus unavailable; refusing disruptive S1 fallback")
        return false
    }

    /** Focus at a normalized Live View coordinate using Creators' App's
     * RemoteTouchOperation path (camera coordinate grid: 640x480). */
    fun driveTouchFocus(normalizedX: Float, normalizedY: Float): Boolean {
        if (!isConnected || !remoteTouchFocusEnabled) return false
        val x = (normalizedX.coerceIn(0f, 1f) * 639f).toInt()
        val y = (normalizedY.coerceIn(0f, 1f) * 479f).toInt()
        val packed = ((x and 0xFFFF) shl 16) or (y and 0xFFFF)
        val startedAt = System.nanoTime()
        // Consume the synchronous PTP response but leave HTTP open. The old
        // close/reopen wrapper turned one touch into a restoring cycle; the
        // earlier no-wait failure was caused by leaving the PTP reply queued,
        // not by the independent HTTP channel existing at the same time.
        val focused = setControlDeviceB(CONTROL_RemoteTouchOperation, packed, 4)
        Log.i(
            TAG,
            "Sony remote touch focus x=$x y=$y focused=$focused " +
                "commandMs=${(System.nanoTime() - startedAt) / 1_000_000L}"
        )
        return focused
    }

    // Device-A property writes use the PTP command socket while Live View
    // uses a separate SSH-forwarded HTTP channel. Keep that stream open for
    // short synchronous property transactions. Closing/reopening HTTP around
    // every EV/ISO/WB/focus-area change created the visible preview gaps.
    fun setIso(value: Int): Boolean = setControlDeviceAStreamingSafe(PROP_ISO, value, 4)
    fun setWhiteBalance(value: Int): Boolean = setControlDeviceAStreamingSafe(PROP_WhiteBalance, value, 2)
    fun setFocusMode(value: Int): Boolean = setControlDeviceAStreamingSafe(PROP_FocusMode, value, 2)
    fun setFocusArea(value: Int): Boolean = setControlDeviceAStreamingSafe(PROP_FocusArea, value, 2)
    fun setExposureMode(value: Int): Boolean =
        setControlDeviceAStreamingSafe(PROP_ExposureMode, value, 4)
    fun setShutterSpeed(numerator: Int, denominator: Int): Boolean {
        require(numerator in 0..0xFFFF && denominator in 0..0xFFFF)
        return setControlDeviceAStreamingSafe(
            PROP_ShutterSpeed,
            ((numerator and 0xFFFF) shl 16) or (denominator and 0xFFFF),
            4
        )
    }
    fun setFNumber(fNumberTimes100: Int): Boolean =
        setControlDeviceAStreamingSafe(PROP_FNumber, fNumberTimes100, 2)
    fun setExposureMeteringMode(value: Int): Boolean =
        setControlDeviceAStreamingSafe(PROP_ExposureMeteringMode, value, 2)
    fun setExposureCompensation(value: Int): Boolean =
        setControlDeviceAStreamingSafe(PROP_ExposureCompensation, value, 2)
    fun setStillFileFormat(value: Int): Boolean =
        setControlDeviceASerialized(PROP_FileFormatStill, value, 2)
    fun setJpegQuality(value: Int): Boolean =
        setControlDeviceASerialized(PROP_JpegQuality, value, 2)
    fun setImageSize(value: Int): Boolean =
        setControlDeviceASerialized(PROP_ImageSize, value, 2)
    fun setStillImageTransferSize(value: Int): Boolean =
        setControlDeviceASerialized(PROP_StillImageTransferSize, value, 2)
    fun setRawFileType(value: Int): Boolean =
        setControlDeviceASerialized(PROP_RawFileType, value, 2)
    fun setAspectRatio(value: Int): Boolean =
        setControlDeviceASerialized(PROP_AspectRatio, value, 2)
    fun setDynamicRangeOptimizer(value: Int): Boolean =
        setControlDeviceASerialized(PROP_DynamicRangeOptimizer, value, 2)
    fun setCreativeLook(value: Int): Boolean =
        setControlDeviceASerialized(PROP_CreativeLook, value, 2)

    /** Apply one coherent camera-quality configuration with HTTP released once.
     * Final still capture passes [includeFocusControls] false: focus is owned
     * by the AF-S + RemoteTouch transaction and must never be reset by an
     * image-format/ISO verification pass immediately before shutter. */
    fun applyQualitySettings(
        settings: SonyQualitySettings,
        includeFocusControls: Boolean = true
    ): Boolean {
        if (!isConnected) return false
        return withLiveViewHttpReleasedForControl {
            val results = linkedMapOf<String, Boolean>()
            settings.stillFileFormat?.let {
                results["stillFileFormat"] = setControlDeviceA(PROP_FileFormatStill, it, 2)
            }
            settings.rawFileType?.let {
                results["rawFileType"] = setControlDeviceA(PROP_RawFileType, it, 2)
            }
            settings.jpegQuality?.let {
                results["jpegQuality"] = setControlDeviceA(PROP_JpegQuality, it, 2)
            }
            settings.imageSize?.let {
                results["imageSize"] = setControlDeviceA(PROP_ImageSize, it, 2)
            }
            settings.stillImageTransferSize?.let {
                results["stillImageTransferSize"] =
                    setControlDeviceA(PROP_StillImageTransferSize, it, 2)
            }
            settings.aspectRatio?.let {
                results["aspectRatio"] = setControlDeviceA(PROP_AspectRatio, it, 2)
            }
            settings.dynamicRangeOptimizer?.let {
                results["dynamicRangeOptimizer"] =
                    setControlDeviceA(PROP_DynamicRangeOptimizer, it, 2)
            }
            settings.creativeLook?.let {
                results["creativeLook"] = setControlDeviceA(PROP_CreativeLook, it, 2)
            }
            results["exposureMode"] = setControlDeviceA(PROP_ExposureMode, settings.exposureMode, 4)
            try { Thread.sleep(60L) } catch (_: InterruptedException) {
                Thread.currentThread().interrupt()
            }
            results["iso"] = setControlDeviceA(PROP_ISO, settings.iso, 4)
            results["whiteBalance"] = setControlDeviceA(PROP_WhiteBalance, settings.whiteBalance, 2)
            settings.fNumberTimes100?.let {
                results["fNumber"] = setControlDeviceA(PROP_FNumber, it, 2)
            }
            if (settings.shutterNumerator != null && settings.shutterDenominator != null) {
                val packed = ((settings.shutterNumerator and 0xFFFF) shl 16) or
                    (settings.shutterDenominator and 0xFFFF)
                results["shutter"] = setControlDeviceA(PROP_ShutterSpeed, packed, 4)
                // Exposure-mode transitions are acknowledged before the
                // shutter mechanism/property table settles. Immediate
                // readback observed the transient 1/50 value after a valid
                // 1/100 ACK. Keep this pre-stream and verify the final value.
                if (results["shutter"] == true &&
                    !waitForPropertyValue(
                        PROP_ShutterSpeed,
                        packed.toLong() and 0xFFFF_FFFFL,
                        QUALITY_PROPERTY_SETTLE_TIMEOUT_MS
                    )
                ) {
                    results["shutter"] = setControlDeviceA(PROP_ShutterSpeed, packed, 4) &&
                        waitForPropertyValue(
                            PROP_ShutterSpeed,
                            packed.toLong() and 0xFFFF_FFFFL,
                            QUALITY_PROPERTY_SETTLE_TIMEOUT_MS
                        )
                }
            }
            results["exposureCompensation"] = setControlDeviceA(
                PROP_ExposureCompensation,
                settings.exposureCompensationMilliEv,
                2
            )
            if (includeFocusControls) {
                results["focusMode"] = setControlDeviceA(PROP_FocusMode, settings.focusMode, 2)
                results["focusArea"] = setControlDeviceA(PROP_FocusArea, settings.focusArea, 2)
            }
            settings.exposureMeteringMode?.let {
                results["metering"] = setControlDeviceA(PROP_ExposureMeteringMode, it, 2)
            }
            val observed = readSonyProperties()
            val expected = linkedMapOf(
                PROP_ExposureMode to settings.exposureMode.toLong(),
                PROP_ISO to (settings.iso.toLong() and 0xFFFF_FFFFL),
                PROP_WhiteBalance to settings.whiteBalance.toLong(),
                PROP_ExposureCompensation to settings.exposureCompensationMilliEv.toLong()
            )
            if (includeFocusControls) {
                expected[PROP_FocusMode] = settings.focusMode.toLong()
            }
            // Focus area is phase-controlled (TAG=Wide, JEWEL=operator area)
            // and the ZV-E10 II reports the prior value for one or more 9209
            // cycles after ACK. It must not reject otherwise-valid RAW/JPEG,
            // ISO, aperture and metering settings or block the shutter.
            settings.stillFileFormat?.let { expected[PROP_FileFormatStill] = it.toLong() }
            settings.rawFileType?.let { expected[PROP_RawFileType] = it.toLong() }
            settings.jpegQuality?.let { expected[PROP_JpegQuality] = it.toLong() }
            settings.imageSize?.let { expected[PROP_ImageSize] = it.toLong() }
            settings.stillImageTransferSize?.let {
                expected[PROP_StillImageTransferSize] = it.toLong()
            }
            settings.aspectRatio?.let { expected[PROP_AspectRatio] = it.toLong() }
            settings.dynamicRangeOptimizer?.let {
                expected[PROP_DynamicRangeOptimizer] = it.toLong()
            }
            settings.creativeLook?.let { expected[PROP_CreativeLook] = it.toLong() }
            settings.fNumberTimes100?.let { expected[PROP_FNumber] = it.toLong() }
            if (settings.shutterNumerator != null && settings.shutterDenominator != null) {
                expected[PROP_ShutterSpeed] =
                    (((settings.shutterNumerator and 0xFFFF) shl 16) or
                        (settings.shutterDenominator and 0xFFFF)).toLong()
            }
            settings.exposureMeteringMode?.let {
                expected[PROP_ExposureMeteringMode] = it.toLong()
            }
            val mismatches = expected.mapNotNull { (code, expectedValue) ->
                val actual = observed[code]?.currentValue
                if (actual == expectedValue) null
                else "0x${code.toString(16)} expected=$expectedValue actual=$actual"
            }
            val ok = results.values.all { it } && mismatches.isEmpty()
            Log.i(
                TAG,
                "Sony quality settings applied ok=$ok results=$results " +
                "mismatches=$mismatches includeFocusControls=$includeFocusControls settings=$settings"
            )
            ok
        }
    }

    /** Optical lens ratio derived from Sony D25D's confirmed 0..100 position. */
    fun zoomRatio(): Float = PRODUCTION_ZOOM_MIN_RATIO +
        (currentOpticalZoomPercent.coerceIn(0, 100) / 100f) *
        (PRODUCTION_ZOOM_MAX_RATIO - PRODUCTION_ZOOM_MIN_RATIO)

    fun setZoomRatio(ratio: Float): Boolean {
        val targetRatio = ratio.coerceIn(PRODUCTION_ZOOM_MIN_RATIO, PRODUCTION_ZOOM_MAX_RATIO)
        val targetPercent = (((targetRatio - PRODUCTION_ZOOM_MIN_RATIO) /
            (PRODUCTION_ZOOM_MAX_RATIO - PRODUCTION_ZOOM_MIN_RATIO)) * 100f)
            .toInt().coerceIn(0, 100)
        return setZoomPercentWithScale(targetPercent)
    }

    /** Creators' App uses writable ZoomScale (D25C) for discrete/automatic
     * zoom. Keep the dedicated Live View channel open: live testing proved
     * DeviceProperty writes and motor zoom complete on the independent PTP
     * lane while preview remains at 25fps. Closing/reopening HTTP for every
     * smooth-zoom sub-step was the source of the repeated "restoring" UI. */
    private fun setZoomPercentWithScale(requestedPercent: Int): Boolean {
        val observed = currentOpticalZoomPercent.coerceIn(0, 100)
        val requested = requestedPercent.coerceIn(0, 100)
        // D25C only accepts 10% steps. Nearest rounding made the first
        // automatic 1.0 -> 1.1x request (~4% travel) round back to 0%, so
        // the pipeline reported zooming forever without moving the lens.
        // Quantize in the requested direction so every non-zero request
        // produces one real optical step.
        val steppedPercent = when {
            requested > observed -> (((requested + 9) / 10) * 10).coerceAtMost(100)
            requested < observed -> ((requested / 10) * 10).coerceAtLeast(0)
            else -> observed
        }
        if (steppedPercent == observed && currentZoomScale in 1_000..2_000) return true
        val targetScale = 1_000 + steppedPercent * 10
        // The caller's single ordered control executor serializes each setter.
        // Consume the synchronous PTP response before accepting another value,
        // without touching the sibling direct-tcpip Live View channel.
        val moved = setControlDeviceARaw(
            PROP_ZoomScale,
            ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN)
                .putInt(targetScale).array()
        )
        if (moved) {
            currentZoomScale = targetScale
            currentOpticalZoomPercent = steppedPercent
        }
        Log.i(
            TAG,
            "Sony ZoomScale target=$targetScale (${steppedPercent}%) " +
                "before=${observed}% moved=$moved"
        )
        return moved
    }

    /** Serialize Sony controls with its permanent HTTP downloader. */
    private inline fun <T> withLiveViewHttpReleasedForControl(action: () -> T): T {
        val releaseStream = liveViewPumpRunning && liveViewStreaming
        if (releaseStream) {
            liveViewControlTransition = true
            lastLiveViewFrameAtNanos = System.nanoTime()
            previousLiveViewSourceFrameAtNanos = 0L
            forceCloseLiveViewChannel()
            closeLiveViewHttpStream()
            try { Thread.sleep(25L) } catch (_: InterruptedException) { }
        }
        return try {
            action()
        } finally {
            if (releaseStream) {
                liveViewControlTransition = false
                synchronized(liveViewSampleMonitor) { liveViewSampleMonitor.notifyAll() }
            }
        }
    }

    private fun opticalZoomPercent(raw: Long?): Int? = raw?.let {
        (it.toInt() and 0xFF).takeIf { percent -> percent in 0..100 }
    }

    fun fetchLiveViewFrameRaw(): ByteArray? {
        if (!isConnected) {
            lastLiveViewDiagnostic =
                "blocked: PTP-IP session is disconnected; reason=$lastDisconnectReason"
            return null
        }
        // Modern Sony PTP3 clients read the virtual live-view object, with
        // ObjectInfo refreshed before every GetObject. The former probe
        // skipped ObjectInfo and was therefore not a valid test of this
        // transport. Keep this as a one-frame diagnostics path until the
        // physical ZV-E10 II proves it stable enough to replace HTTP.
        closeLiveViewHttpStream()
        // Do not refresh 0x9209 here. This body supplies D221 during the
        // successful bootstrap but stops answering 0x9209 after the remote
        // session settles; making it a prerequisite destroyed the command
        // tunnel before ObjectInfo could even be tested.
        val liveViewStatus = currentLiveViewStatus
        if (liveViewStatus == null || liveViewStatus == 0L) {
            lastLiveViewDiagnostic =
                "Sony D221 live-view status=${liveViewStatus ?: "missing"}; virtual object not ready"
            return null
        }
        val info = executeOperation(PTP_OC_GetObjectInfo, intArrayOf(LIVEVIEW_OBJECT_HANDLE))
        if (!info.isOk) {
            lastLiveViewDiagnostic =
                "GetObjectInfo(0xFFFFC002) response=0x${info.code.toString(16)} " +
                    "data=${info.data.size}B connected=$isConnected"
            Log.w(TAG, "Sony PTP live-view $lastLiveViewDiagnostic")
            return null
        }
        val frame = executeOperation(PTP_OC_GetObject, intArrayOf(LIVEVIEW_OBJECT_HANDLE))
        if (!frame.isOk || frame.data.isEmpty()) {
            lastLiveViewDiagnostic =
                "GetObject(0xFFFFC002) response=0x${frame.code.toString(16)} " +
                    "data=${frame.data.size}B connected=$isConnected"
            Log.w(TAG, "Sony PTP live-view $lastLiveViewDiagnostic")
            return null
        }
        val jpeg = extractJpeg(frame.data)
        lastLiveViewDiagnostic =
            "D221=0x${liveViewStatus.toString(16)}; ObjectInfo=${info.data.size}B; " +
                "GetObject=0x${frame.code.toString(16)}/${frame.data.size}B; JPEG=${jpeg?.size ?: 0}B"
        Log.i(
            TAG,
            "Sony PTP live-view probe $lastLiveViewDiagnostic"
        )
        return jpeg
    }

    /** Live View uses its own SSH-forwarded HTTP channel. PTP controls remain
     * available concurrently for zoom, focus, exposure and shutter. */
    fun setLiveViewStreaming(enabled: Boolean) {
        liveViewStreaming = enabled
        if (enabled) {
            startLiveViewPump()
        } else {
            stopLiveViewPump()
        }
    }

    /** Briefly closes only the HTTP image channel for a physical control.
     * The logical streaming flag stays true so the PTP keepalive never
     * races a focus/zoom/shutter operation during this short pause. */
    fun pauseLiveViewHttpForControl() {
        // Stop the pump, not just the socket: leaving the reader thread alive
        // would have it immediately reopen the channel it is meant to yield
        // for the duration of the physical control operation.
        stopLiveViewPump()
    }

    /**
     * Refreshes Sony's remote-session lease without replacing the PTP/IP
     * session. The ZV-E10 II withholds 0x9209 while the HTTP preview is
     * open, so close only that lightweight channel, poll once, then let the
     * next [fetchLiveViewJpeg] reopen it. This avoids the multi-second full
     * SSH/PTP handshake that made production preview visibly freeze every
     * 70 seconds.
     */
    fun refreshLiveViewLease(): Boolean {
        if (!isConnected) return false
        // Must go through forceCloseLiveViewChannel(), not
        // closeLiveViewHttpStream() directly: this runs on the
        // SonyProductionLiveView loop thread while SonyLiveViewPump reads
        // liveViewChannel/liveViewIn concurrently on its own
        // thread. Nulling those fields from here without coordination raced
        // against the pump's own read/reopen cycle. forceCloseLiveViewChannel
        // only disconnects the channel (safe from any thread, same as the
        // stall watchdog uses); the pump's own catch block then does the
        // full close+reopen exactly like any other read failure.
        forceCloseLiveViewChannel()
        return try {
            val refreshed = readSonyProperties().isNotEmpty()
            if (refreshed) {
                Log.i(TAG, "Sony remote lease refreshed; HTTP preview will resume")
            } else {
                Log.w(TAG, "Sony remote lease refresh returned no properties")
            }
            refreshed
        } catch (e: Exception) {
            Log.w(TAG, "Sony remote lease refresh failed: ${e.message}")
            false
        }
    }

    /**
     * Retrieves one JPEG from the persistent IP Live View stream advertised
     * by Sony property 0xD278. On Access-Authentication bodies such as the
     * ZV-E10 II, that URL points at localhost inside the camera and requires
     * a separate SSH direct-tcpip channel. The USB-only GetObject(0xFFFFC002)
     * path stalls this body's PTP-IP command channel and must not be used.
     */
    fun fetchLiveViewJpeg(): ByteArray? {
        val sample = fetchLatestLiveViewSample() ?: return null
        return sample.jpeg
    }

    /**
     * Blocks until a Live View frame NEWER than the one this caller last
     * received is available, then returns it. Starts the pump on first use.
     * Always returns the newest frame the camera has produced, never a queued
     * older one -- see the pump's design note above for why that matters.
     */
    fun fetchLatestLiveViewSample(): LiveViewSample? {
        if (!isConnected) return null
        if (!startLiveViewPump()) return null
        val sample = awaitLatestLiveViewFrame(lastServedSequence, LIVE_VIEW_READ_TIMEOUT_MS)
            ?: return null
        lastServedSequence = sample.sequence
        liveViewDecodedCount.incrementAndGet()
        return sample
    }

    /** Age of the supplied frame at this instant -- the honest end-to-end
     * latency contribution of transport plus consumer backlog. */
    fun liveViewSampleAgeMs(sample: LiveViewSample): Long =
        (System.nanoTime() - sample.receivedAtNanos) / 1_000_000L

    /** Starts the single stream-owning reader thread. Idempotent. */
    fun startLiveViewPump(): Boolean {
        synchronized(liveViewPumpLock) {
            if (liveViewPumpRunning) return true
            if (!isConnected) return false
            // Already gave up for this exact session -- do not silently
            // restart the same doomed HTTP storm. Caller (production loop)
            // must observe repeated null frames and trigger a full reconnect,
            // which is what actually clears this (see connectBlocking).
            if (liveViewPumpFailedEpoch == connectionEpoch.get()) return false
            liveViewPumpRunning = true
            liveViewStreaming = true
            // The first HTTP open owns recovery until it either supplies a
            // frame or fails. Do not let the watchdog race channel creation.
            liveViewRecoveryActive.set(true)
            lastLiveViewFrameAtNanos = 0L
            liveViewSlowGapCount.set(0L)
            liveViewMaxGapMs.set(0L)
            val epoch = connectionEpoch.get()
            liveViewPumpThread = thread(name = "SonyLiveViewPump", isDaemon = true) {
                Process.setThreadPriority(Process.THREAD_PRIORITY_DISPLAY)
                runLiveViewPump(epoch)
            }
            return true
        }
    }

    /**
     * Stops the pump. Critically, the SSH channel is disconnected WITHOUT
     * holding [liveViewLock]: the pump thread can be parked inside a blocking
     * InputStream.read(), and the old code's stop path tried to take the very
     * lock that thread held, so a wedged read could never be cancelled.
     * Disconnecting the channel from outside makes that read throw, which is
     * the only reliable way to unblock it.
     */
    fun stopLiveViewPump() {
        val thread: Thread?
        synchronized(liveViewPumpLock) {
            liveViewPumpRunning = false
            liveViewRecoveryActive.set(false)
            thread = liveViewPumpThread
            liveViewPumpThread = null
        }
        forceCloseLiveViewChannel()
        synchronized(liveViewSampleMonitor) { liveViewSampleMonitor.notifyAll() }
        if (thread != null && thread !== Thread.currentThread()) {
            try { thread.join(1_000L) } catch (_: InterruptedException) {}
        }
        closeLiveViewHttpStream()
        latestLiveViewSample.set(null)
        lastServedSequence = 0L
        liveViewPrimed = false
    }

    /** Disconnects the Live View channel without taking [liveViewLock], so a
     * thread blocked in read() can always be released. */
    private fun forceCloseLiveViewChannel() {
        try { liveViewIn?.close() } catch (_: Exception) {}
        try { liveViewChannel?.disconnect() } catch (_: Exception) {}
    }

    private fun runLiveViewPump(epoch: Int) {
        var consecutiveTransportFailures = 0
        var consecutiveHttpRejects = 0
        var retryBudgetExhausted = false
        while (liveViewPumpRunning && isConnected && epoch == connectionEpoch.get()) {
            if (liveViewControlTransition) {
                try { Thread.sleep(10L) } catch (_: InterruptedException) { break }
                continue
            }
            try {
                lastLiveViewHttpRetryableReject = false
                if (!ensureLiveViewHttpStream()) {
                    liveViewRecoveryActive.set(true)
                    if (lastLiveViewHttpRetryableReject) {
                        consecutiveHttpRejects += 1
                    } else {
                        consecutiveTransportFailures += 1
                        consecutiveHttpRejects = 0
                    }
                    val httpBudgetSpent = consecutiveHttpRejects >= LIVE_VIEW_MAX_HTTP_REJECTS
                    val transportBudgetSpent =
                        consecutiveTransportFailures >= LIVE_VIEW_MAX_TRANSPORT_FAILURES
                    if (httpBudgetSpent || transportBudgetSpent) {
                        retryBudgetExhausted = true
                        Log.w(
                            TAG,
                            "Live View pump escalating to full session reconnect: " +
                                "transportFailures=$consecutiveTransportFailures " +
                                "httpRejects=$consecutiveHttpRejects"
                        )
                        break
                    }
                    Thread.sleep(LIVE_VIEW_REOPEN_RETRY_DELAY_MS)
                    continue
                }
                // A newly opened stream gets a fresh watchdog interval. The
                // gate is released only after open succeeds, never while an
                // HTTP 503/direct-tcpip retry is still in progress.
                if (liveViewRecoveryActive.getAndSet(false)) {
                    lastLiveViewFrameAtNanos = System.nanoTime()
                }
                val input = liveViewIn ?: continue
                // No pacing sleep here on purpose: this thread must drain the
                // socket as fast as the camera fills it, or the backlog this
                // whole design exists to prevent starts rebuilding.
                val frame = readNextLiveViewFrame(input)
                consecutiveTransportFailures = 0
                consecutiveHttpRejects = 0
                liveViewRecoveryActive.set(false)
                liveViewPrimed = true
                val receivedAtNanos = System.nanoTime()
                val previousReceivedAtNanos = previousLiveViewSourceFrameAtNanos
                if (previousReceivedAtNanos > 0L) {
                    val gapMs = (receivedAtNanos - previousReceivedAtNanos) / 1_000_000L
                    if (gapMs >= LIVE_VIEW_SLOW_GAP_MS) {
                        liveViewSlowGapCount.incrementAndGet()
                    }
                    liveViewMaxGapMs.accumulateAndGet(gapMs, ::maxOf)
                }
                previousLiveViewSourceFrameAtNanos = receivedAtNanos
                lastLiveViewFrameAtNanos = receivedAtNanos
                val sequence = liveViewSourceSequence.incrementAndGet()
                val previous = latestLiveViewSample.getAndSet(
                    LiveViewSample(
                        sequence,
                        frame.jpeg,
                        receivedAtNanos,
                        frame.focusIndication
                    )
                )
                // Overwriting a frame the consumer never took is a DROP, not
                // an error -- it is the pump doing its job. Counting it is how
                // we tell "consumer is slower than source" from "source slow".
                if (previous != null && previous.sequence > lastServedSequence) {
                    liveViewDroppedBeforeDecode.incrementAndGet()
                }
                synchronized(liveViewSampleMonitor) { liveViewSampleMonitor.notifyAll() }
            } catch (e: Exception) {
                if (!liveViewPumpRunning || !isConnected) break
                if (liveViewControlTransition) {
                    closeLiveViewHttpStream()
                    while (liveViewControlTransition && liveViewPumpRunning && isConnected &&
                        epoch == connectionEpoch.get()
                    ) {
                        try { Thread.sleep(10L) } catch (_: InterruptedException) { break }
                    }
                    consecutiveTransportFailures = 0
                    consecutiveHttpRejects = 0
                    liveViewRecoveryActive.set(false)
                    continue
                }
                consecutiveTransportFailures += 1
                consecutiveHttpRejects = 0
                liveViewPrimed = false
                Log.w(TAG, "Live View pump read failed: ${e.message}")
                closeLiveViewHttpStream()
                if (liveViewRecoveryActive.compareAndSet(false, true)) {
                    liveViewReopenCount.incrementAndGet()
                }
                if (consecutiveTransportFailures >= LIVE_VIEW_MAX_TRANSPORT_FAILURES) {
                    retryBudgetExhausted = true
                    Log.w(
                        TAG,
                        "Live View replacement stream failed; escalating to full session reconnect"
                    )
                    break
                }
                try { Thread.sleep(LIVE_VIEW_REOPEN_RETRY_DELAY_MS) } catch (_: InterruptedException) { break }
            }
        }
        // Latch this epoch as exhausted so a subsequent
        // fetchLatestLiveViewSample() call cannot silently kick off a second
        // full retry storm against the same dead producer/session -- see the
        // field comment on liveViewPumpFailedEpoch above.
        // An intentional capture/control pause also exits this loop after
        // stopLiveViewPump() clears liveViewPumpRunning. Do not poison the
        // still-healthy session in that case. Latch only a genuinely spent
        // HTTP retry budget; otherwise preview can resume on the same SSH/PTP
        // session immediately after the original has downloaded.
        if (retryBudgetExhausted && isConnected && epoch == connectionEpoch.get()) {
            liveViewPumpFailedEpoch = epoch
        }
        liveViewPumpRunning = false
        liveViewRecoveryActive.set(false)
        synchronized(liveViewSampleMonitor) { liveViewSampleMonitor.notifyAll() }
        Log.i(TAG, "Live View pump stopped")
    }

    private fun awaitLatestLiveViewFrame(afterSequence: Long, timeoutMs: Long): LiveViewSample? {
        val deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(timeoutMs)
        synchronized(liveViewSampleMonitor) {
            while (true) {
                val sample = latestLiveViewSample.get()
                if (sample != null && sample.sequence > afterSequence) return sample
                if (!liveViewPumpRunning || !isConnected) return null
                val remaining = deadline - System.nanoTime()
                if (remaining <= 0L) return null
                try {
                    liveViewSampleMonitor.wait(
                        remaining / 1_000_000L,
                        (remaining % 1_000_000L).toInt()
                    )
                } catch (_: InterruptedException) {
                    return null
                }
            }
        }
    }

    /** Rolling transport counters. Source vs decoded vs dropped is the only
     * honest way to tell a real 30 FPS pipeline from a fast-looking one that
     * is replaying stale frames. */
    fun liveViewTelemetry(): String {
        val sample = latestLiveViewSample.get()
        val age = sample?.let { liveViewSampleAgeMs(it) } ?: -1L
        return "source=${liveViewSourceSequence.get()} decoded=${liveViewDecodedCount.get()} " +
            "dropped=${liveViewDroppedBeforeDecode.get()} reopens=${liveViewReopenCount.get()} " +
            "watchdogTrips=${liveViewWatchdogTripCount.get()} " +
            "slowGaps=${liveViewSlowGapCount.get()} maxGapMs=${liveViewMaxGapMs.get()} " +
            "latestAgeMs=$age pump=$liveViewPumpRunning " +
            "recovering=${liveViewRecoveryActive.get()} tunnel=" +
            (if (liveViewSshSession != null) "dedicated" else "shared")
    }

    fun liveViewSourceFrameCount(): Long = liveViewSourceSequence.get()
    fun liveViewDroppedFrameCount(): Long = liveViewDroppedBeforeDecode.get()

    private fun ensureLiveViewHttpStream(): Boolean {
        if (liveViewChannel?.isConnected == true && liveViewIn != null) {
            return true
        }
        closeLiveViewHttpStream()

        val advertisedUrl = liveViewUrl?.takeIf { it.isNotBlank() } ?: run {
            liveViewUrl = readSonyProperties()[PROP_LiveViewUrl]?.currentString
            liveViewUrl
        } ?: return false
        val uri = try {
            URI(advertisedUrl)
        } catch (e: Exception) {
            Log.w(TAG, "Invalid Sony LiveViewURL: $advertisedUrl", e)
            return false
        }
        if (!uri.scheme.equals("http", ignoreCase = true)) {
            Log.w(TAG, "Unsupported Sony LiveViewURL scheme: ${uri.scheme}")
            return false
        }
        val port = if (uri.port > 0) uri.port else 80
        if (port !in 1..65535) return false
        if (port != LIVE_VIEW_REMOTE_PORT) {
            Log.w(TAG, "Unexpected Sony Live View port: $port")
            return false
        }
        val liveTunnel = liveViewSshSession ?: sshSession
        if (liveTunnel?.isConnected != true) return false

        val rawPath = uri.rawPath?.takeIf { it.isNotEmpty() } ?: "/"
        val requestTarget = if (uri.rawQuery.isNullOrEmpty()) {
            rawPath
        } else {
            "$rawPath?${uri.rawQuery}"
        }
        val channel = try {
            (liveTunnel.openChannel("direct-tcpip") as ChannelDirectTCPIP).apply {
                setHost(TUNNEL_HOST)
                setPort(LIVE_VIEW_REMOTE_PORT)
                setOrgIPAddress("127.0.0.1")
                setOrgPort(0)
                tuneTunnelChannelWindow(this, SSH_LIVE_VIEW_WINDOW_BYTES)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Sony Live View direct-tcpip channel creation failed: ${e.message}")
            return false
        }
        val rawInput: BufferedInputStream
        val rawOutput: OutputStream
        try {
            rawInput = BufferedInputStream(channel.inputStream, 256 * 1024)
            rawOutput = channel.outputStream
            liveViewChannel = channel
            liveViewOut = rawOutput
            channel.connect(LIVE_VIEW_READ_TIMEOUT_MS.toInt())
            val request = buildString {
                append("GET ").append(requestTarget).append(" HTTP/1.1\r\n")
                append("Host: ").append(TUNNEL_HOST).append(':').append(LIVE_VIEW_REMOTE_PORT).append("\r\n")
                append("Accept: */*\r\n")
                append("Connection: close\r\n\r\n")
            }.toByteArray(Charsets.ISO_8859_1)
            rawOutput.write(request)
            rawOutput.flush()
        } catch (e: Exception) {
            Log.w(TAG, "Sony Live View direct-tcpip connection failed: ${e.message}")
            closeLiveViewHttpStream()
            return false
        }

        val headers = try {
            readHttpHeaders(rawInput)
        } catch (e: Exception) {
            Log.w(TAG, "Sony Live View HTTP response failed: ${e.message}")
            closeLiveViewHttpStream()
            return false
        }
        val statusLine = headers.lineSequence().firstOrNull().orEmpty()
        val responseCode = Regex("""^HTTP/\d(?:\.\d)?\s+(\d{3})""")
            .find(statusLine)?.groupValues?.getOrNull(1)?.toIntOrNull()
        if (responseCode != 200) {
            Log.w(TAG, "Sony Live View HTTP rejected: $statusLine")
            // Only 503 is a known temporary Sony producer state. A different
            // HTTP status is not plausibly repaired by repeating the same
            // request against the same session.
            lastLiveViewHttpRetryableReject = responseCode == 503
            closeLiveViewHttpStream()
            return false
        }
        val chunked = headers.lineSequence().any { line ->
            line.startsWith("Transfer-Encoding:", ignoreCase = true) &&
                line.contains("chunked", ignoreCase = true)
        }
        liveViewIn = if (chunked) HttpChunkedInputStream(rawInput) else rawInput
        Log.i(
            TAG,
            "Sony persistent Live View HTTP stream connected via direct-tcpip " +
                "window=1MB packet=64KB chunked=$chunked"
        )
        return true
    }

    /** JSch's direct-tcpip defaults are only a 128KB receive window and 16KB
     * packet. The Sony stream is continuous; enlarge both before channel-open
     * so WINDOW_ADJUST is not required every few 42KB frames. These methods
     * are package-private in JSch, hence the narrow reflection bridge. */
    private fun tuneTunnelChannelWindow(channel: ChannelDirectTCPIP, windowBytes: Int) {
        try {
            val base = Channel::class.java
            base.getDeclaredMethod("setLocalWindowSizeMax", Int::class.javaPrimitiveType).apply {
                isAccessible = true
                invoke(channel, windowBytes)
            }
            base.getDeclaredMethod("setLocalWindowSize", Int::class.javaPrimitiveType).apply {
                isAccessible = true
                invoke(channel, windowBytes)
            }
            base.getDeclaredMethod("setLocalPacketSize", Int::class.javaPrimitiveType).apply {
                isAccessible = true
                invoke(channel, SSH_CHANNEL_PACKET_BYTES)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Sony SSH window tuning unavailable: ${e.message}")
        }
    }

    private class HttpChunkedInputStream(private val source: InputStream) : InputStream() {
        private var chunkRemaining = 0
        private var needsChunkTerminator = false
        private var finished = false
        private val oneByte = ByteArray(1)

        override fun read(): Int {
            val count = read(oneByte, 0, 1)
            return if (count < 0) -1 else oneByte[0].toInt() and 0xFF
        }

        override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
            if (length == 0) return 0
            if (finished) return -1
            if (chunkRemaining == 0) {
                if (needsChunkTerminator) {
                    expectByte('\r'.code)
                    expectByte('\n'.code)
                }
                val sizeLine = readAsciiLine()
                val sizeText = sizeLine.substringBefore(';').trim()
                chunkRemaining = sizeText.toIntOrNull(16)
                    ?: throw IllegalStateException("Invalid HTTP chunk size: $sizeLine")
                if (chunkRemaining == 0) {
                    // Consume optional trailer fields through the empty line.
                    while (readAsciiLine().isNotEmpty()) { }
                    finished = true
                    return -1
                }
                needsChunkTerminator = true
            }
            val requested = minOf(length, chunkRemaining)
            val count = source.read(buffer, offset, requested)
            if (count < 0) throw java.io.EOFException("HTTP chunk ended early")
            if (count == 0) return 0
            chunkRemaining -= count
            return count
        }

        private fun readAsciiLine(): String {
            val bytes = java.io.ByteArrayOutputStream(32)
            while (bytes.size() < 8 * 1024) {
                val value = source.read()
                if (value < 0) throw java.io.EOFException("HTTP chunk header ended early")
                if (value == '\r'.code) {
                    expectByte('\n'.code)
                    return bytes.toString(Charsets.US_ASCII.name())
                }
                bytes.write(value)
            }
            throw IllegalStateException("HTTP chunk header exceeded 8KB")
        }

        private fun expectByte(expected: Int) {
            val actual = source.read()
            if (actual != expected) {
                throw IllegalStateException("Invalid HTTP chunk delimiter: $actual != $expected")
            }
        }
    }

    private fun readHttpHeaders(input: InputStream): String {
        val bytes = java.io.ByteArrayOutputStream(1024)
        val deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(LIVE_VIEW_READ_TIMEOUT_MS)
        var match = 0
        val terminator = byteArrayOf(13, 10, 13, 10)
        while (bytes.size() < 16 * 1024) {
            val value = readAvailableByte(input, deadline)
            bytes.write(value)
            match = if (value == (terminator[match].toInt() and 0xFF)) match + 1 else 0
            if (match == terminator.size) {
                return bytes.toString(Charsets.ISO_8859_1.name())
            }
        }
        throw IllegalStateException("Sony Live View HTTP headers exceeded 16KB")
    }

    /**
     * Reads Sony's exact HTTP LiveViewDataset framing, matching Creators'
     * App's AbstractEeImageDownloader. Each frame starts with four UINT32LE
     * fields: image offset/size and focal-info offset/size. Reading by those
     * lengths is cheaper and safer than scanning JPEG marker bytes, and the
     * focal block supplies the camera's real AF-C state every frame.
     */
    private fun readNextLiveViewFrame(input: InputStream): LiveViewFrame {
        val readStartedAtNanos = System.nanoTime()
        val header = ByteArray(16)
        readFullyBlocking(input, header)
        val headerReadAtNanos = System.nanoTime()
        val imageOffset = header.readIntLeAt(0)
        val imageSize = header.readIntLeAt(4)
        val focalOffset = header.readIntLeAt(8)
        val focalSize = header.readIntLeAt(12)

        val valid = imageOffset >= 16 && focalOffset >= 16 &&
            imageSize in 4..LIVE_VIEW_MAX_JPEG_BYTES &&
            focalSize in 0..LIVE_VIEW_MAX_FOCAL_INFO_BYTES
        if (!valid) {
            throw IllegalStateException(
                "Invalid Sony LiveViewDataset header image=$imageOffset/$imageSize " +
                    "focal=$focalOffset/$focalSize bytes=${header.toHex()}"
            )
        }
        val datasetSize = maxOf(
            imageOffset.toLong() + imageSize.toLong(),
            focalOffset.toLong() + focalSize.toLong()
        )
        if (datasetSize !in 16L..LIVE_VIEW_MAX_DATASET_BYTES.toLong()) {
            throw IllegalStateException(
                "Sony LiveViewDataset exceeded bounds: $datasetSize header=${header.toHex()}"
            )
        }
        val dataset = ByteArray(datasetSize.toInt())
        System.arraycopy(header, 0, dataset, 0, header.size)
        readFullyBlocking(input, dataset, header.size, dataset.size - header.size)
        val bodyReadAtNanos = System.nanoTime()

        val totalReadMs = (bodyReadAtNanos - readStartedAtNanos) / 1_000_000L
        val nowNanos = bodyReadAtNanos
        val lastSlowLog = lastSlowDatasetLogAtNanos.get()
        if (
            totalReadMs >= LIVE_VIEW_SLOW_GAP_MS &&
            nowNanos - lastSlowLog >= 1_000_000_000L &&
            lastSlowDatasetLogAtNanos.compareAndSet(lastSlowLog, nowNanos)
        ) {
            val headerReadMs = (headerReadAtNanos - readStartedAtNanos) / 1_000_000L
            val bodyReadMs = (bodyReadAtNanos - headerReadAtNanos) / 1_000_000L
            Log.w(
                TAG,
                "Sony Live View slow dataset read totalMs=$totalReadMs " +
                    "headerMs=$headerReadMs bodyMs=$bodyReadMs datasetBytes=$datasetSize " +
                    "jpegBytes=$imageSize focalBytes=$focalSize"
            )
        }

        val jpeg = dataset.copyOfRange(imageOffset, imageOffset + imageSize)
        if (jpeg.size < 4 || jpeg[0] != 0xFF.toByte() || jpeg[1] != 0xD8.toByte()) {
            throw IllegalStateException("Sony LiveViewDataset image is not JPEG")
        }
        val focus = if (focalSize >= 12 && focalOffset + 12 <= dataset.size) {
            // Focal block: UINT16 version, UINT8 coordinate type, 5 reserved,
            // then UINT32LE AfLockStatus. Exact layout from Creators' App.
            dataset.readIntLeAt(focalOffset + 8).takeIf {
                it == 1 || it == 2 || it == 3 || it == 5 || it == 6 || it == 7
            }
        } else null
        if (focus != null && lastLoggedFocalState.getAndSet(focus) != focus) {
            Log.i(TAG, "Sony focal-info state=$focus")
        }
        return LiveViewFrame(jpeg, focus)
    }

    private fun readFullyBlocking(
        input: InputStream,
        target: ByteArray,
        start: Int = 0,
        length: Int = target.size - start
    ) {
        var offset = start
        val end = start + length
        while (offset < end) {
            if (liveViewChannel?.isConnected != true) {
                throw java.io.EOFException("Sony Live View HTTP connection closed")
            }
            val count = input.read(target, offset, end - offset)
            if (count < 0) throw java.io.EOFException("Sony Live View HTTP stream closed")
            if (count == 0) continue
            offset += count
        }
    }

    /** Legacy marker scanner retained only for controlled diagnostics. */
    private fun readNextLiveViewJpeg(input: InputStream): ByteArray {
        val deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(LIVE_VIEW_READ_TIMEOUT_MS)
        var bytes = ByteArray(maxOf(256 * 1024, liveViewCarry.size + LIVE_VIEW_READ_CHUNK_BYTES))
        var size = liveViewCarry.size
        if (size > 0) System.arraycopy(liveViewCarry, 0, bytes, 0, size)
        liveViewCarry = ByteArray(0)
        var jpegStart = -1
        var scanFrom = 1

        fun ensureCapacity(required: Int) {
            if (required <= bytes.size) return
            var capacity = bytes.size
            while (capacity < required && capacity < LIVE_VIEW_MAX_JPEG_BYTES) {
                capacity = (capacity * 2).coerceAtMost(LIVE_VIEW_MAX_JPEG_BYTES)
            }
            if (capacity < required) {
                throw IllegalStateException("Sony Live View JPEG exceeded ${LIVE_VIEW_MAX_JPEG_BYTES}B")
            }
            bytes = bytes.copyOf(capacity)
        }

        while (true) {
            for (index in scanFrom until size) {
                val previous = bytes[index - 1].toInt() and 0xFF
                val current = bytes[index].toInt() and 0xFF
                if (jpegStart < 0) {
                    if (previous == 0xFF && current == 0xD8) jpegStart = index - 1
                } else if (previous == 0xFF && current == 0xD9) {
                    val endExclusive = index + 1
                    val jpeg = bytes.copyOfRange(jpegStart, endExclusive)
                    liveViewCarry = bytes.copyOfRange(endExclusive, size)
                    return jpeg
                }
            }
            scanFrom = maxOf(1, size)

            if (liveViewChannel?.isConnected != true) {
                throw java.io.EOFException("Sony Live View HTTP connection closed")
            }
            if (System.nanoTime() >= deadline) {
                throw SocketTimeoutException("Sony Live View frame timed out after ${LIVE_VIEW_READ_TIMEOUT_MS}ms")
            }
            val readSize = LIVE_VIEW_READ_CHUNK_BYTES
            ensureCapacity(size + readSize)
            // A/B test against the former available()+2ms polling loop.
            // JSch's channel InputStream blocks until SSH payload arrives;
            // draining it directly also gives JSch immediate buffer space
            // when a JPEG spans multiple SSH channel windows.
            val count = input.read(bytes, size, readSize)
            if (count < 0) throw java.io.EOFException("Sony Live View HTTP stream closed")
            size += count
        }
    }

    private fun readAvailableByte(input: InputStream, deadlineNanos: Long): Int {
        while (true) {
            if (input.available() > 0) {
                val value = input.read()
                if (value < 0) throw java.io.EOFException("Sony Live View HTTP stream closed")
                return value
            }
            if (liveViewChannel?.isConnected != true) {
                throw java.io.EOFException("Sony Live View HTTP connection closed")
            }
            if (System.nanoTime() >= deadlineNanos) {
                throw SocketTimeoutException("Sony Live View frame timed out after ${LIVE_VIEW_READ_TIMEOUT_MS}ms")
            }
            Thread.sleep(2L)
        }
    }

    private fun closeLiveViewHttpStream() = synchronized(liveViewLock) {
        val input = liveViewIn
        val output = liveViewOut
        val channel = liveViewChannel
        liveViewIn = null
        liveViewOut = null
        liveViewChannel = null
        try { input?.close() } catch (_: Exception) {}
        try { output?.close() } catch (_: Exception) {}
        try { channel?.disconnect() } catch (_: Exception) {}
        liveViewCarry = ByteArray(0)
    }

    /** Finds a complete embedded JPEG, tolerating a Sony metadata prefix. */
    private fun extractJpeg(data: ByteArray): ByteArray? {
        if (data.size < 5) return null
        var start = -1
        for (i in 0 until data.size - 2) {
            if (data[i] == 0xFF.toByte() && data[i + 1] == 0xD8.toByte() && data[i + 2] == 0xFF.toByte()) {
                start = i
                break
            }
        }
        if (start < 0) return null
        var endExclusive = -1
        for (i in data.size - 2 downTo start + 2) {
            if (data[i] == 0xFF.toByte() && data[i + 1] == 0xD9.toByte()) {
                endExclusive = i + 2
                break
            }
        }
        if (endExclusive <= start) return null
        return if (start == 0 && endExclusive == data.size) data else data.copyOfRange(start, endExclusive)
    }

    // ---- Low-level PTP-IP framing (over the SSH-tunneled channel) ------

    private fun setControlDeviceA(propCode: Int, value: Int, byteWidth: Int): Boolean {
        if (!isConnected) return false
        val payload = ByteBuffer.allocate(byteWidth).order(ByteOrder.LITTLE_ENDIAN)
        when (byteWidth) {
            1 -> payload.put(value.toByte())
            2 -> payload.putShort(value.toShort())
            4 -> payload.putInt(value)
        }
        return setControlDeviceARaw(propCode, payload.array())
    }

    /** Execute one property write on Sony's single serialized control path. */
    private fun setControlDeviceASerialized(propCode: Int, value: Int, byteWidth: Int): Boolean {
        if (!isConnected) return false
        val payload = ByteBuffer.allocate(byteWidth).order(ByteOrder.LITTLE_ENDIAN)
        when (byteWidth) {
            1 -> payload.put(value.toByte())
            2 -> payload.putShort(value.toShort())
            4 -> payload.putInt(value)
            else -> throw IllegalArgumentException("Unsupported ControlDeviceA width: $byteWidth")
        }
        return withLiveViewHttpReleasedForControl {
            setControlDeviceARaw(propCode, payload.array())
        }
    }

    /** Short property transaction on Sony's independent PTP command lane.
     * The response is still consumed synchronously; only the sibling HTTP
     * channel remains open, preventing a needless Live View reopen. */
    private fun setControlDeviceAStreamingSafe(propCode: Int, value: Int, byteWidth: Int): Boolean {
        if (!isConnected) return false
        val payload = ByteBuffer.allocate(byteWidth).order(ByteOrder.LITTLE_ENDIAN)
        when (byteWidth) {
            1 -> payload.put(value.toByte())
            2 -> payload.putShort(value.toShort())
            4 -> payload.putInt(value)
            else -> throw IllegalArgumentException("Unsupported ControlDeviceA width: $byteWidth")
        }
        return setControlDeviceARaw(propCode, payload.array())
    }

    private fun setControlDeviceARaw(propCode: Int, payload: ByteArray): Boolean =
        operationWithData(OC_SetControlDeviceA, devicePropertyOperationParams(propCode), payload)

    private fun setControlDeviceB(propCode: Int, value: Int, byteWidth: Int = 2): Boolean {
        if (!isConnected) return false
        val payload = when (byteWidth) {
            1 -> byteArrayOf(value.toByte())
            2 -> ByteBuffer.allocate(2).order(ByteOrder.LITTLE_ENDIAN).putShort(value.toShort()).array()
            4 -> ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(value).array()
            else -> throw IllegalArgumentException("Unsupported ControlDeviceB width: $byteWidth")
        }
        // Creators' App selects the option flag from the SDI vendor version:
        // version >=310 uses [propertyCode, 1], older versions use only
        // [propertyCode]. The old hardcoded [propertyCode, 0] was neither
        // form and caused the ZV-E10 II to defer live S1/zoom responses.
        return operationWithData(
            OC_SetControlDeviceB,
            devicePropertyOperationParams(propCode),
            payload
        )
    }

    /** Writes one 0x9207 transaction without waiting for its response. */
    private fun sendControlDeviceBNoWait(propCode: Int, value: Int, byteWidth: Int): Int {
        if (!isConnected) throw IllegalStateException("Sony is disconnected")
        val payload = when (byteWidth) {
            1 -> byteArrayOf(value.toByte())
            2 -> ByteBuffer.allocate(2).order(ByteOrder.LITTLE_ENDIAN)
                .putShort(value.toShort()).array()
            4 -> ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN)
                .putInt(value).array()
            else -> throw IllegalArgumentException("Unsupported ControlDeviceB width: $byteWidth")
        }
        val txId = sendOperationRequest(
            OC_SetControlDeviceB,
            devicePropertyOperationParams(propCode),
            DP_DATA_OUT
        )
        sendDataPhase(txId, payload)
        return txId
    }

    private fun usesDevicePropertyOption(): Boolean = sdiVendorCodeVersion >= 310

    private fun devicePropertyOperationParams(propCode: Int): IntArray =
        if (usesDevicePropertyOption()) intArrayOf(propCode, 1) else intArrayOf(propCode)

    /** Consumes already-arrived responses without ever delaying control. */
    private fun drainDeferredControlResponses(transactionIds: List<Int>) {
        val input = controlIn ?: return
        for (txId in transactionIds) {
            if (input.available() < 4) break
            try {
                readOperationResult(txId)
            } catch (e: Exception) {
                Log.d(TAG, "Deferred control response txId=$txId not ready: ${e.message}")
                break
            }
        }
    }

    private fun operationNoData(opcode: Int, params: IntArray): Boolean {
        return executeOperation(opcode, params).isOk
    }

    private fun operationWithData(opcode: Int, params: IntArray, data: ByteArray): Boolean {
        return executeOperation(opcode, params, data).isOk
    }

    private data class OperationResult(
        val code: Int,
        val transactionId: Int?,
        val params: List<Int>,
        val data: ByteArray
    ) {
        val isOk: Boolean get() = code == 0x2001
    }

    private data class SonyPropertyState(
        val code: Int,
        val dataType: Int,
        val writable: Boolean,
        val enabled: Boolean,
        val currentValue: Long?,
        val currentString: String?,
        val minimumValue: Long? = null,
        val maximumValue: Long? = null,
        val stepSize: Long? = null,
        val supportedValues: List<Long> = emptyList()
    )

    private data class PtpValueRead(
        val value: Long?,
        val stringValue: String?,
        val nextOffset: Int
    )

    private fun readSonyProperties(): Map<Int, SonyPropertyState> {
        // Creators' App requests the normal property dataset with leading
        // parameter 0 and, for negotiated SDI >=310, option flag 1.
        val params = if (usesDevicePropertyOption()) intArrayOf(0, 1) else intArrayOf(0)
        val result = executeOperation(OC_SDIOGetAllExtDeviceInfo, params)
        if (!result.isOk) return emptyMap()
        val properties = parseSonyProperties(result.data)
        properties[PROP_LiveViewStatus]?.currentValue?.let { currentLiveViewStatus = it }
        properties[PROP_ShootingFileInfo]?.currentValue?.let { currentShootingFileInfo = it }
        for (code in intArrayOf(
            PROP_DriveMode,
            PROP_ShootingFileInfo,
            PROP_LiveViewStatus,
            PROP_SaveMedia,
            PROP_PositionKey,
            PROP_LiveViewUrl,
            PROP_AutoFocus,
            PROP_Capture,
            PROP_ZoomStep,
            PROP_LiveViewQuality,
            PROP_FocusMode,
            PROP_FocusIndication,
            PROP_FocusArea,
            PROP_FunctionOfTouchOperation,
            PROP_RemoteTouchOperationEnable,
            PROP_CancelRemoteTouchOperationEnable,
            PROP_ISO,
            PROP_WhiteBalance,
            PROP_ExposureMeteringMode,
            PROP_ExposureMode,
            PROP_ShutterSpeed,
            PROP_FNumber,
            PROP_ExposureCompensation,
            PROP_ZoomScale,
            PROP_ZoomOptical
        )) {
            properties[code]?.let {
                Log.d(
                    TAG,
                    "Sony prop 0x${code.toString(16)} value=${it.currentString ?: it.currentValue} " +
                        "enabled=${it.enabled} writable=${it.writable} type=0x${it.dataType.toString(16)} " +
                        "range=${it.minimumValue}..${it.maximumValue}/${it.stepSize} " +
                        "values=${it.supportedValues}"
                )
            }
        }
        return properties
    }

    /** Parse Sony's version-3 SDIDevicePropInfoDataset stream (0x9209). */
    private fun parseSonyProperties(data: ByteArray): Map<Int, SonyPropertyState> {
        if (data.size < 8) return emptyMap()
        val datasetCount = ByteBuffer.wrap(data, 0, 8).order(ByteOrder.LITTLE_ENDIAN).long
        if (datasetCount < 0 || datasetCount > 10_000) return emptyMap()
        val parsed = LinkedHashMap<Int, SonyPropertyState>()
        var offset = 8

        repeat(datasetCount.toInt()) {
            if (offset + 6 > data.size) return@repeat
            val code = data.readU16LeAt(offset); offset += 2
            val dataType = data.readU16LeAt(offset); offset += 2
            val writable = data[offset++].toInt() != 0
            val enabled = data[offset++].toInt() != 0

            val defaultRead = readPtpValue(data, offset, dataType) ?: return parsed
            offset = defaultRead.nextOffset
            val currentRead = readPtpValue(data, offset, dataType) ?: return parsed
            offset = currentRead.nextOffset
            if (offset >= data.size) return parsed
            val formFlag = data[offset++].toInt() and 0xFF
            val scalarType = if (dataType in 0x4001..0x400A) dataType - 0x4000 else dataType
            var minimumValue: Long? = null
            var maximumValue: Long? = null
            var stepSize: Long? = null
            val supportedValues = ArrayList<Long>()

            when (formFlag) {
                1 -> {
                    val minimum = readPtpValue(data, offset, scalarType) ?: return parsed
                    offset = minimum.nextOffset
                    val maximum = readPtpValue(data, offset, scalarType) ?: return parsed
                    offset = maximum.nextOffset
                    val step = readPtpValue(data, offset, scalarType) ?: return parsed
                    offset = step.nextOffset
                    minimumValue = minimum.value
                    maximumValue = maximum.value
                    stepSize = step.value
                }
                2 -> {
                    if (offset + 2 > data.size) return parsed
                    val firstCount = data.readU16LeAt(offset); offset += 2
                    repeat(firstCount) {
                        val enumValue = readPtpValue(data, offset, scalarType) ?: return parsed
                        offset = enumValue.nextOffset
                        enumValue.value?.let(supportedValues::add)
                    }
                    // Version 3 always carries a second enumeration block.
                    if (offset + 2 > data.size) return parsed
                    val secondCount = data.readU16LeAt(offset); offset += 2
                    repeat(secondCount) {
                        val enumValue = readPtpValue(data, offset, scalarType) ?: return parsed
                        offset = enumValue.nextOffset
                    }
                }
            }

            parsed[code] = SonyPropertyState(
                code = code,
                dataType = dataType,
                writable = writable,
                enabled = enabled,
                currentValue = currentRead.value,
                currentString = currentRead.stringValue,
                minimumValue = minimumValue,
                maximumValue = maximumValue,
                stepSize = stepSize,
                supportedValues = supportedValues
            )
        }
        return parsed
    }

    private fun readPtpValue(data: ByteArray, offset: Int, dataType: Int): PtpValueRead? {
        if (offset < 0 || offset >= data.size) return null
        if (dataType == 0xFFFF) {
            val characterCount = data[offset].toInt() and 0xFF
            val end = offset + 1 + characterCount * 2
            if (end > data.size) return null
            val decoded = if (characterCount == 0) {
                ""
            } else {
                String(
                    data,
                    offset + 1,
                    characterCount * 2,
                    Charsets.UTF_16LE
                ).trimEnd('\u0000')
            }
            return PtpValueRead(null, decoded, end)
        }
        if (dataType in 0x4001..0x400A) {
            if (offset + 4 > data.size) return null
            val count = data.readU32LeAt(offset)
            if (count < 0 || count > 1_000_000) return null
            var next = offset + 4
            val scalarType = dataType - 0x4000
            repeat(count.toInt()) {
                val element = readPtpValue(data, next, scalarType) ?: return null
                next = element.nextOffset
            }
            return PtpValueRead(null, null, next)
        }

        val size = when (dataType) {
            0x0001, 0x0002 -> 1
            0x0003, 0x0004 -> 2
            0x0005, 0x0006 -> 4
            0x0007, 0x0008 -> 8
            0x0009, 0x000A -> 16
            else -> return null
        }
        if (offset + size > data.size) return null
        var value: Long? = null
        if (size <= 8) {
            var decoded = 0L
            for (i in 0 until size) {
                decoded = decoded or ((data[offset + i].toLong() and 0xFFL) shl (8 * i))
            }
            // PTP type codes alternate signed/unsigned. Sony exposes EV as
            // INT16, so -0.3 EV arrives as 0xFED4 and must be -300, not 65236.
            value = when (dataType) {
                0x0001 -> decoded.toByte().toLong()
                0x0003 -> decoded.toShort().toLong()
                0x0005 -> decoded.toInt().toLong()
                else -> decoded
            }
        }
        return PtpValueRead(value, null, offset + size)
    }

    private fun waitForPropertyEnabled(propCode: Int, timeoutMs: Long): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (hasOpenControlTransport() && System.currentTimeMillis() < deadline) {
            val state = readSonyProperties()[propCode]
            if (state?.enabled == true) return true
            Thread.sleep(100L)
        }
        return false
    }

    private fun waitForPropertyValue(propCode: Int, expected: Long, timeoutMs: Long): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (hasOpenControlTransport() && System.currentTimeMillis() < deadline) {
            val state = readSonyProperties()[propCode]
            if (state?.currentValue == expected) return true
            Thread.sleep(100L)
        }
        return false
    }

    private fun waitForShootingFileReadyEventFirst(timeoutMs: Long): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        var lastPropertyFallbackAt = 0L
        while (hasOpenControlTransport() && System.currentTimeMillis() < deadline) {
            val event = eventQueue.poll(250L, TimeUnit.MILLISECONDS)
            if (event != null && event.size >= 2) {
                val code = event.readU16LeAt(0)
                if (code == PTP_EC_ObjectAdded || code == PTP_EC_SonyObjectAdded) {
                    Log.d(TAG, "Sony single ObjectAdded event=0x${code.toString(16)}")
                    return true
                }
            }
            val now = System.currentTimeMillis()
            if (now - lastPropertyFallbackAt >= 500L) {
                lastPropertyFallbackAt = now
                val value = readSonyProperties()[PROP_ShootingFileInfo]?.currentValue ?: 0L
                if (sonyBufferedCaptureCount(value) > 0) return true
            }
        }
        return false
    }

    /** True during the handshake and normal operation; false immediately
     * after disconnect clears the command channel. */
    private fun hasOpenControlTransport(): Boolean =
        controlChannel?.isConnected == true && controlIn != null && controlOut != null

    private fun executeOperation(
        opcode: Int,
        params: IntArray = intArrayOf(),
        dataOut: ByteArray? = null
    ): OperationResult = synchronized(operationLock) {
        try {
            val dataPhase = if (dataOut == null) DP_NO_DATA_OR_DATA_IN else DP_DATA_OUT
            val txId = sendOperationRequest(opcode, params, dataPhase)
            if (dataOut != null) sendDataPhase(txId, dataOut)
            readOperationResult(txId)
        } catch (e: Exception) {
            // A stale/closed camera tunnel must fail the action, not crash
            // the app's worker thread. Mark disconnected so a zoom finally
            // block cannot send a second packet into the dead stream.
            Log.w(TAG, "Operation 0x${opcode.toString(16)} failed: ${e.message}", e)
            disconnect(
                "operation 0x${opcode.toString(16)} failed: " +
                    (e.message ?: e.javaClass.simpleName)
            )
            OperationResult(0, null, emptyList(), byteArrayOf())
        }
    }

    /** Init Command Request: GUID(16) + FriendlyName(UTF-16LE, null-term)
     * + ProtocolVersion(4 bytes: UInt16 major, UInt16 minor). The trailing
     * version field is the one most summarized PTP-IP references omit --
     * see class doc comment for how expensive that omission was to find. */
    private fun sendInitCommandRequest(guid: ByteArray, name: String) {
        val nameBytes = utf16leNullTerminated(name)
        val version = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putShort(1).putShort(0).array()
        val body = ByteBuffer.allocate(guid.size + nameBytes.size + version.size).order(ByteOrder.LITTLE_ENDIAN)
        body.put(guid); body.put(nameBytes); body.put(version)
        writePacket(controlOut!!, PKT_INIT_COMMAND_REQUEST, body.array())
    }

    /** Returns the connection number on success, null on failure. */
    private fun readInitCommandAck(): Int? {
        val input = controlIn ?: return null
        val length = input.readIntLe()
        val type = input.readIntLe()
        val body = ByteArray(length - 8)
        readFullyFrom(input, body)
        if (type != PKT_INIT_COMMAND_ACK) return null
        return ByteBuffer.wrap(body, 0, 4).order(ByteOrder.LITTLE_ENDIAN).int
    }

    private fun sendInitEventRequest(out: OutputStream, connId: Int) {
        val body = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(connId).array()
        writePacket(out, PKT_INIT_EVENT_REQUEST, body)
    }

    private fun readPacketType(input: InputStream): Int {
        val length = input.readIntLe()
        val type = input.readIntLe()
        val body = ByteArray(length - 8)
        readFullyFrom(input, body)
        return type
    }

    private fun sendOperationRequest(
        opcode: Int,
        params: IntArray,
        dataPhaseInfo: Int = DP_NO_DATA_OR_DATA_IN
    ): Int {
        val txId = transactionId.getAndIncrement()
        // CIPA DC-X005: DataPhaseInfo(4) + OperationCode(2) +
        // TransactionID(4) + Params(4 each). There is NO reserved UInt16
        // after OperationCode. The previous extra two zero bytes shifted
        // TransactionID and every parameter on the wire; for small txIds
        // Sony consequently decoded every request as transaction 0.
        val body = ByteBuffer.allocate(10 + params.size * 4).order(ByteOrder.LITTLE_ENDIAN)
        body.putInt(dataPhaseInfo)
        body.putShort(opcode.toShort())
        body.putInt(txId)
        for (p in params) body.putInt(p)
        val bytes = body.array()
        Log.i(
            TAG,
            "TX operation opcode=0x${opcode.toString(16)} txId=$txId " +
                "dataPhase=$dataPhaseInfo params=${params.contentToString()} body=${bytes.toHex()}"
        )
        synchronized(controlWriteLock) {
            writePacket(controlOut!!, PKT_OPERATION_REQUEST, bytes)
        }
        return txId
    }

    private fun sendDataPhase(txId: Int, data: ByteArray) {
        Log.i(TAG, "TX data txId=$txId size=${data.size} body=${data.toHex()}")
        val startBody = ByteBuffer.allocate(12).order(ByteOrder.LITTLE_ENDIAN)
        startBody.putInt(txId); startBody.putLong(data.size.toLong())
        synchronized(controlWriteLock) {
            writePacket(controlOut!!, PKT_START_DATA_PACKET, startBody.array())
        }

        // Match Creators' App's OperationRequesterDataOut exactly. For these
        // short SDIO control payloads it sends StartDataPacket followed by one
        // EndDataPacket containing all data; it does not insert a DataPacket
        // followed by an empty EndDataPacket. The latter left this camera's
        // remote-control transaction pending and its HTTP producer wedged.
        val endBody = ByteBuffer.allocate(4 + data.size).order(ByteOrder.LITTLE_ENDIAN)
        endBody.putInt(txId); endBody.put(data)
        synchronized(controlWriteLock) {
            writePacket(controlOut!!, PKT_END_DATA_PACKET, endBody.array())
        }
    }

    private fun readOperationResult(expectedTxId: Int): OperationResult {
        val input = controlIn ?: return OperationResult(0, null, emptyList(), byteArrayOf())
        val data = java.io.ByteArrayOutputStream()
        val completed = AtomicBoolean(false)
        val lastProgressAtNanos = AtomicLong(System.nanoTime())
        val epoch = connectionEpoch.get()
        thread(name = "SonyPtpIpCommandProbe", isDaemon = true) {
            try { Thread.sleep(1_000L) } catch (_: InterruptedException) { return@thread }
            if (completed.get() || epoch != connectionEpoch.get()) return@thread
            try {
                synchronized(controlWriteLock) {
                    if (!completed.get() && epoch == connectionEpoch.get()) {
                        controlOut?.let { writePacket(it, PKT_PROBE_REQUEST, ByteArray(0)) }
                    }
                }
                Log.d(TAG, "Sony command ProbeRequest sent txId=$expectedTxId")
            } catch (e: Exception) {
                Log.d(TAG, "Sony command ProbeRequest failed txId=$expectedTxId: ${e.message}")
            }
        }
        thread(name = "SonyPtpIpCommandWatchdog", isDaemon = true) {
            while (!completed.get() && epoch == connectionEpoch.get()) {
                try { Thread.sleep(250L) } catch (_: InterruptedException) { return@thread }
                val idleMs = (System.nanoTime() - lastProgressAtNanos.get()) / 1_000_000L
                if (!completed.get() && idleMs >= PTP_READ_TIMEOUT_MS) {
                    Log.w(TAG, "Sony command txId=$expectedTxId stalled ${idleMs}ms; closing control channel")
                    try { controlChannel?.disconnect() } catch (_: Exception) { }
                    return@thread
                }
            }
        }
        // Throttles per-chunk logging for large transfers (2026-08-26 fix):
        // every PTP data packet used to get its own Log.i() call, string
        // formatting included, synchronously on this read thread before the
        // next chunk could even be read. That's harmless for a ~9KB property
        // dump (a handful of chunks) but a 10-18MB original photo download
        // is the SAME code path with potentially hundreds to thousands of
        // small PTP chunks -- the logging tax, not network/WiFi throughput,
        // was very likely the dominant cost of that transfer. Logs every
        // chunk in full for the first LOG_ALL_CHUNKS_UNDER (covers all real
        // control-op sizes), then throttles to periodic progress so a bulk
        // download's actual read loop isn't fighting its own diagnostics.
        var chunkIndex = 0
        var lastLoggedChunkIndex = 0
        try {
            while (true) {
            // Creators' TcpConnection owns one permanent blocking receiver.
            // Do the same here. Polling InputStream.available() worked during
            // bootstrap but starved command responses while the sibling HTTP
            // SSH channel was busy, making every live control wait 12 seconds.
            val length = input.readIntLeBlocking()
            val type = input.readIntLeBlocking()
            if (length < 8 || length > 128 * 1024 * 1024) {
                throw IllegalStateException("Invalid PTP-IP packet length $length for type $type")
            }
            val body = ByteArray(length - 8)
            readFullyBlockingPtp(input, body)
            lastProgressAtNanos.set(System.nanoTime())
            when (type) {
                PKT_START_DATA_PACKET -> {
                    val txId = if (body.size >= 4) body.readIntLeAt(0) else null
                    val total = if (body.size >= 12) {
                        ByteBuffer.wrap(body, 4, 8).order(ByteOrder.LITTLE_ENDIAN).long
                    } else null
                    Log.i(TAG, "RX data-start txId=$txId expectedTxId=$expectedTxId total=$total")
                }
                PKT_DATA_PACKET, PKT_END_DATA_PACKET -> {
                    chunkIndex += 1
                    val txId = if (body.size >= 4) body.readIntLeAt(0) else null
                    if (body.size > 4) data.write(body, 4, body.size - 4)
                    val isEnd = type == PKT_END_DATA_PACKET
                    // Full detail for the first LOG_ALL_CHUNKS_UNDER chunks
                    // (every real control op fits inside that), the END
                    // packet always, and otherwise only every
                    // LOG_CHUNK_STRIDE-th chunk -- a bulk original-photo
                    // download can be hundreds to thousands of small PTP
                    // chunks, and logging every one of them synchronously
                    // was very likely the dominant cost of that transfer,
                    // not WiFi/tablet throughput.
                    if (chunkIndex <= LOG_ALL_CHUNKS_UNDER || isEnd ||
                        chunkIndex - lastLoggedChunkIndex >= LOG_CHUNK_STRIDE
                    ) {
                        lastLoggedChunkIndex = chunkIndex
                        Log.i(
                            TAG,
                            "RX data-${if (isEnd) "end" else "chunk"} " +
                                "txId=$txId expectedTxId=$expectedTxId chunk=${(body.size - 4).coerceAtLeast(0)}B " +
                                "accumulated=${data.size()}B chunkIndex=$chunkIndex"
                        )
                    }
                }
                PKT_OPERATION_RESPONSE -> {
                    val code = ByteBuffer.wrap(body, 0, 2).order(ByteOrder.LITTLE_ENDIAN).short.toInt() and 0xFFFF
                    val echoedTxId = if (body.size >= 6) {
                        ByteBuffer.wrap(body, 2, 4).order(ByteOrder.LITTLE_ENDIAN).int
                    } else null
                    val params = if (body.size > 6 && (body.size - 6) % 4 == 0) {
                        val parsed = ArrayList<Int>()
                        val fields = ByteBuffer.wrap(body, 6, body.size - 6).order(ByteOrder.LITTLE_ENDIAN)
                        while (fields.remaining() >= 4) parsed.add(fields.int)
                        parsed
                    } else emptyList()
                    val message = "RX operation code=0x${code.toString(16)} " +
                        "txId=$echoedTxId expectedTxId=$expectedTxId params=$params " +
                        "data=${data.size()}B body=${body.toHex()}"
                    if (echoedTxId != expectedTxId) {
                        // A paired 0x9207 control can reply after its release
                        // transaction. Consume that stale response and keep
                        // reading until this operation's own txId arrives.
                        Log.w(TAG, "$message (deferred response skipped)")
                        data.reset()
                        continue
                    }
                    if (code == 0x2001) Log.i(TAG, message) else Log.w(TAG, message)
                    return OperationResult(code, echoedTxId, params, data.toByteArray())
                }
                PKT_PROBE_REQUEST -> {
                    synchronized(controlWriteLock) {
                        controlOut?.let { writePacket(it, PKT_PROBE_RESPONSE, ByteArray(0)) }
                    }
                    Log.d(TAG, "Sony command ProbeRequest answered txId=$expectedTxId")
                }
                PKT_PROBE_RESPONSE ->
                    Log.d(TAG, "Sony command ProbeResponse received txId=$expectedTxId")
                else -> Log.w(TAG, "Unexpected packet type $type waiting for operation response")
            }
        }
        } finally {
            completed.set(true)
        }
    }

    private fun writePacket(out: OutputStream, type: Int, body: ByteArray) {
        val header = ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN)
        header.putInt(8 + body.size); header.putInt(type)
        out.write(header.array())
        out.write(body)
        out.flush()
    }

    private fun ByteArray.toHex(): String = joinToString(separator = "") { "%02x".format(it.toInt() and 0xFF) }

    private fun ByteArray.readIntLeAt(offset: Int): Int =
        ByteBuffer.wrap(this, offset, 4).order(ByteOrder.LITTLE_ENDIAN).int

    private fun ByteArray.readU16LeAt(offset: Int): Int =
        ByteBuffer.wrap(this, offset, 2).order(ByteOrder.LITTLE_ENDIAN).short.toInt() and 0xFFFF

    private fun ByteArray.readU32LeAt(offset: Int): Long =
        readIntLeAt(offset).toLong() and 0xFFFF_FFFFL

    private fun InputStream.readIntLe(timeoutMs: Long? = PTP_READ_TIMEOUT_MS): Int {
        val b = ByteArray(4)
        readFullyFrom(this, b, timeoutMs)
        return ByteBuffer.wrap(b).order(ByteOrder.LITTLE_ENDIAN).int
    }

    private fun InputStream.readIntLeBlocking(): Int {
        val bytes = ByteArray(4)
        readFullyBlockingPtp(this, bytes)
        return ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).int
    }

    private fun readFullyBlockingPtp(input: InputStream, target: ByteArray) {
        var offset = 0
        while (offset < target.size) {
            val count = input.read(target, offset, target.size - offset)
            if (count < 0) {
                throw java.io.EOFException(
                    "Sony command stream closed after $offset/${target.size} bytes"
                )
            }
            if (count > 0) offset += count
        }
    }

    private fun readFullyFrom(
        input: InputStream,
        buf: ByteArray,
        timeoutMs: Long? = PTP_READ_TIMEOUT_MS
    ) {
        var offset = 0
        var deadline = timeoutMs?.let {
            System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(it)
        }
        while (offset < buf.size) {
            val available = input.available()
            if (available <= 0) {
                if (deadline != null && System.nanoTime() >= deadline) {
                    throw SocketTimeoutException(
                        "PTP read timed out after ${timeoutMs}ms ($offset/${buf.size} bytes)"
                    )
                }
                Thread.sleep(5L)
                continue
            }
            val n = input.read(buf, offset, minOf(buf.size - offset, available))
            if (n < 0) throw java.io.EOFException("Stream closed after $offset/${buf.size} bytes")
            offset += n
            // Progress earns a fresh timeout window for the next chunk.
            deadline = timeoutMs?.let {
                System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(it)
            }
        }
    }

    private fun startEventReaderThread() {
        val input = eventIn ?: return
        val epoch = connectionEpoch.get()
        eventThreadRunning = true
        thread(name = "SonyPtpIpEventReader", isDaemon = true) {
            try {
                while (eventThreadRunning && epoch == connectionEpoch.get()) {
                    // Event traffic can legitimately be idle for minutes;
                    // only the command channel gets the bounded read timeout.
                    val length = input.readIntLe(timeoutMs = null)
                    val type = input.readIntLe(timeoutMs = null)
                    val body = ByteArray(length - 8)
                    readFullyFrom(input, body, timeoutMs = null)
                    when (type) {
                        PKT_EVENT -> eventQueue.offer(body)
                        PKT_PROBE_REQUEST -> {
                            // Sony Creators installs this responder immediately
                            // after InitEventAck. Ignoring the camera's probe lets
                            // its PTP/live-view lease expire about 32 seconds later.
                            // A probe packet has only the standard 8-byte header.
                            eventOut?.let { writePacket(it, PKT_PROBE_RESPONSE, ByteArray(0)) }
                            Log.d(TAG, "Sony PTP/IP ProbeRequest answered")
                        }
                    }
                }
            } catch (e: Exception) {
                if (eventThreadRunning && epoch == connectionEpoch.get()) {
                    Log.w(TAG, "Event reader stopped: ${e.message}")
                }
            }
        }
    }

    private fun startKeepAliveThread() {
        if (keepAliveThreadRunning) return
        val epoch = connectionEpoch.get()
        keepAliveThreadRunning = true
        thread(name = "SonyPtpIpKeepAlive", isDaemon = true) {
            var lastHealthLogAtNanos = 0L
            while (keepAliveThreadRunning && isConnected && epoch == connectionEpoch.get()) {
                try {
                    Thread.sleep(TRANSPORT_HEALTH_POLL_MS)
                } catch (_: InterruptedException) {
                    break
                }
                if (!keepAliveThreadRunning || !isConnected || epoch != connectionEpoch.get()) break

                // Never use a PTP operation as an idle heartbeat on this
                // ZV-E10 II. Repeated GetDeviceInfo and 0x9209 both stop
                // receiving responses once the remote session is settled;
                // executeOperation then correctly tears down the timed-out
                // transport, which previously made CaptureCam disconnect
                // itself every 15 seconds. JSch's serverAliveInterval keeps
                // SSH active. Streaming supplies continuous HTTP traffic.
                // Here we only observe local tunnel health without touching
                // Sony's single serialized PTP command channel.
                if (sshSession?.isConnected != true || !hasOpenControlTransport()) {
                    disconnect("SSH/PTP tunnel health check failed")
                    break
                }

                // Live View stall watchdog. readNextLiveViewJpeg() can only
                // check its own deadline BEFORE it blocks, so a read that
                // parks forever is invisible to it. Disconnecting the channel
                // from here (a different thread, holding no read lock) makes
                // that read throw, and the pump reopens on its next loop.
                if (liveViewPumpRunning && !liveViewControlTransition &&
                    !liveViewRecoveryActive.get()
                ) {
                    val lastFrameAt = lastLiveViewFrameAtNanos
                    val sinceFrameMs = if (lastFrameAt == 0L) 0L else
                        (System.nanoTime() - lastFrameAt) / 1_000_000L
                    if (lastFrameAt != 0L && sinceFrameMs > LIVE_VIEW_STALL_TIMEOUT_MS &&
                        liveViewRecoveryActive.compareAndSet(false, true)
                    ) {
                        Log.w(
                            TAG,
                            "Live View stalled ${sinceFrameMs}ms; starting single-flight channel recovery"
                        )
                        liveViewWatchdogTripCount.incrementAndGet()
                        liveViewReopenCount.incrementAndGet()
                        forceCloseLiveViewChannel()
                    }
                }
                // TRIED AND REVERTED (2026-08-24): a lightweight SDIOConnect
                // re-handshake at 65s, attempting to preempt the measured
                // ~82-84s hard session boundary. Result: it got stuck
                // fighting the pump's own concurrent HTTP-reopen retries for
                // the SAME underlying SSH session/control channel, took
                // ~12s to even fail, returned false, and the drop happened
                // at the same ~80s mark regardless -- strictly worse than
                // doing nothing (added a stuck period on top of the
                // unavoidable drop). Do not re-attempt a proactive refresh
                // of any kind without first solving the "runs concurrently
                // with the pump's own retry loop" contention problem --
                // that's the actual blocker, not the specific opcode used
                // (this ruled out SDIOConnect the same way an earlier
                // attempt ruled out 0x9209).
                val nowNanos = System.nanoTime()
                if (nowNanos - lastHealthLogAtNanos >=
                    TimeUnit.MILLISECONDS.toNanos(TRANSPORT_HEALTH_LOG_MS)
                ) {
                    lastHealthLogAtNanos = nowNanos
                    Log.d(TAG, "Sony tunnel health OK; ${liveViewTelemetry()}")
                }
            }
        }
    }

    fun pollEvent(timeoutMs: Long): ByteArray? =
        eventQueue.poll(timeoutMs, TimeUnit.MILLISECONDS)

    private fun uuidToBytes(uuid: UUID): ByteArray {
        val bb = ByteBuffer.allocate(16)
        bb.putLong(uuid.mostSignificantBits)
        bb.putLong(uuid.leastSignificantBits)
        return bb.array()
    }

    private fun utf16leNullTerminated(s: String): ByteArray {
        val bb = ByteBuffer.allocate((s.length + 1) * 2).order(ByteOrder.LITTLE_ENDIAN)
        for (c in s) bb.putShort(c.code.toShort())
        bb.putShort(0)
        return bb.array()
    }
}
