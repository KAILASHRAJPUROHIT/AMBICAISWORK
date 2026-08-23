package com.aradhana.capturecam

import android.util.Log
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlin.concurrent.thread

/**
 * Direct PTP-IP client for Sony Alpha-family cameras (confirmed target:
 * ZV-E10 II) -- talks to the camera's own PTP-IP service over WiFi (the
 * camera acts as its own access point in "PC Remote"/"Smart Remote
 * Control" mode), bypassing Sony's Creators' App and its Android-only
 * Camera Remote SDK (which explicitly does NOT support Android -- confirmed
 * 2026-08-23 against Sony's own SDK docs: macOS/Windows-x86/Linux only).
 *
 * PTP-IP itself is an open standard (CIPA DC-X005 / ISO 15740 companion
 * transport spec) -- port, packet framing, and handshake sequence below are
 * the public spec, not anything Sony-proprietary. What IS Sony-proprietary
 * (and reverse engineered rather than documented) is everything under the
 * "Sony SDIO extension" section: the 0x92xx opcodes, 0xD2xx property codes,
 * and the exact SDIOConnect 3-phase handshake sequence. Source for those:
 * cross-referenced from two independent, real-device-verified open source
 * projects rather than guessed --
 *   - frank26080115/alpha-fairy (arduino_workspace/libraries/PtpIpCamera/*)
 *     -- built by Wireshark-capturing Sony's own Imaging Edge Remote app
 *   - olkham/pysonycam (constants.py) -- independent USB-PTP implementation
 * Both agree on the opcode/property table, which is why this is a real
 * implementation attempt rather than speculative code -- but neither
 * project has been run against a ZV-E10 II specifically (alpha-fairy's
 * confirmed list is A1/A6600/A6000/RX100M4/RX0M2), so some property VALUE
 * encodings (not the opcodes themselves) may need adjustment once tested
 * live against this exact body. Treat DEFAULT_CAMERA_IP and any property
 * value ranges as first-draft, not final, until confirmed on real hardware.
 */
class SonyPtpIpController {

    companion object {
        private const val TAG = "SonyPtpIp"
        private const val PTPIP_PORT = 15740

        // Sony's camera-as-AP mode has historically defaulted its own
        // gateway address to one of a few fixed values depending on
        // firmware/app generation. 192.168.100.1 was found directly inside
        // Sony's own Creators' App native library strings (libmonitor_
        // protocol_pf.so, 2026-08-23 strings dump) alongside .2/.3/.4 --
        // consistent with "camera is the AP, phone/laptop is a DHCP client
        // in that /24". Fails over to the classic 192.168.122.1 (used by
        // many other Sony/Canon/etc PTP-IP-over-WiFi camera APs) if the
        // first guess doesn't answer.
        val CANDIDATE_CAMERA_IPS = listOf("192.168.100.1", "192.168.122.1", "192.168.1.1")

        // --- PTP-IP packet types (CIPA DC-X005 public spec, not Sony-specific) ---
        private const val PKT_INIT_COMMAND_REQUEST = 1
        private const val PKT_INIT_COMMAND_ACK = 2
        private const val PKT_INIT_EVENT_REQUEST = 3
        private const val PKT_INIT_EVENT_ACK = 4
        private const val PKT_INIT_FAIL = 5
        private const val PKT_OPERATION_REQUEST = 6
        private const val PKT_OPERATION_RESPONSE = 7
        private const val PKT_EVENT = 8
        private const val PKT_START_DATA_PACKET = 9
        private const val PKT_DATA_PACKET = 10
        private const val PKT_CANCEL_TRANSACTION = 11
        private const val PKT_END_DATA_PACKET = 12

        // --- Standard PTP opcodes ---
        private const val PTP_OC_GetDeviceInfo = 0x1001
        private const val PTP_OC_OpenSession = 0x1002
        private const val PTP_OC_CloseSession = 0x1003
        private const val PTP_OC_GetStorageIDs = 0x1004
        private const val PTP_OC_GetObject = 0x1009

        // --- Sony SDIO extension opcodes (reverse engineered, see class doc) ---
        private const val OC_SDIOConnect = 0x9201
        private const val OC_SDIOGetExtDeviceInfo = 0x9202
        private const val OC_SonyGetDevicePropDesc = 0x9203
        private const val OC_SonyGetDevicePropValue = 0x9204
        private const val OC_SetControlDeviceA = 0x9205
        private const val OC_GetControlDeviceDesc = 0x9206
        private const val OC_SetControlDeviceB = 0x9207
        private const val OC_GetAllDevicePropData = 0x9209

        // --- Sony SDIO property codes actually used by this controller ---
        const val PROP_AutoFocus = 0xD2C1        // S1 (half-press) -- 2=engage, 1=release
        const val PROP_Capture = 0xD2C2          // S2 (full-press) -- 2=engage, 1=release
        const val PROP_ISO = 0xD21E
        const val PROP_ShutterSpeed = 0xD20D
        const val PROP_FNumber = 0x5007          // standard PTP DPC, Sony reuses it
        const val PROP_ExposureMode = 0x500E
        const val PROP_ExposureCompensation = 0x5010
        const val PROP_WhiteBalance = 0x5005
        const val PROP_FocusMode = 0x500A
        const val PROP_ZoomStep = 0xD2DD         // signed step; sign = direction
        const val PROP_LiveViewStatus = 0xD221

        const val ZOOM_TELE_STEP: Short = -1
        const val ZOOM_WIDE_STEP: Short = 1

        private const val SDI_VERSION_V3 = 0x012C // 300 -- matches pysonycam's SDI_VERSION_V3

        // Sony's "live view image" is fetched the same way as any other PTP
        // object, using this fixed pseudo-handle rather than a real object
        // ID from a content listing -- consistent across every independent
        // Sony PTP-IP reverse-engineering project found (alpha-fairy,
        // pysonycam, and older libgphoto2/gphoto2 Sony live-view code all
        // use this same handle).
        private const val LIVEVIEW_OBJECT_HANDLE = 0xFFFFC002.toInt()
    }

    private var controlSocket: Socket? = null
    private var eventSocket: Socket? = null
    private var controlOut: DataOutputStream? = null
    private var controlIn: DataInputStream? = null
    private var eventIn: DataInputStream? = null
    private val transactionId = AtomicInteger(1)
    private val eventQueue = LinkedBlockingQueue<ByteArray>()
    @Volatile private var eventThreadRunning = false

    @Volatile var isConnected: Boolean = false
        private set
    var connectedIp: String? = null
        private set

    /**
     * Blocking connect -- run this off the main thread (a background
     * Handler/thread), NOT on the UI thread. Tries each candidate IP in
     * turn since the actual AP gateway address for this exact camera/app
     * generation isn't confirmed yet (see CANDIDATE_CAMERA_IPS doc).
     * Returns true once the full SDIO handshake (GetDeviceInfo ->
     * GetStorageIDs -> SDIOConnect x3 phases -> GetExtDeviceInfo) has
     * completed successfully.
     */
    fun connectBlocking(friendlyName: String = "CaptureCam", timeoutMs: Int = 4000): Boolean {
        for (ip in CANDIDATE_CAMERA_IPS) {
            Log.i(TAG, "Trying camera at $ip:$PTPIP_PORT")
            if (tryConnectTo(ip, friendlyName, timeoutMs)) {
                connectedIp = ip
                return true
            }
            disconnect()
        }
        return false
    }

    private fun tryConnectTo(ip: String, friendlyName: String, timeoutMs: Int): Boolean {
        try {
            val ctrl = Socket()
            ctrl.connect(InetSocketAddress(ip, PTPIP_PORT), timeoutMs)
            controlSocket = ctrl
            controlOut = DataOutputStream(ctrl.getOutputStream())
            controlIn = DataInputStream(ctrl.getInputStream())

            val guid = uuidToBytes(UUID.randomUUID())
            sendInitCommandRequest(guid, friendlyName)
            val (pktType, connId) = readInitCommandAck() ?: run {
                Log.w(TAG, "No/bad Init Command Ack from $ip")
                return false
            }
            if (pktType != PKT_INIT_COMMAND_ACK) {
                Log.w(TAG, "Expected Init Command Ack, got type $pktType")
                return false
            }

            val evt = Socket()
            evt.connect(InetSocketAddress(ip, PTPIP_PORT), timeoutMs)
            eventSocket = evt
            val eventOut = DataOutputStream(evt.getOutputStream())
            eventIn = DataInputStream(evt.getInputStream())
            sendInitEventRequest(eventOut, connId)
            val eventAckType = readPacketType(eventIn!!)
            if (eventAckType != PKT_INIT_EVENT_ACK) {
                Log.w(TAG, "Expected Init Event Ack, got type $eventAckType")
                return false
            }

            startEventReaderThread()

            // Standard PTP session open before any Sony-specific calls.
            if (!operationNoData(PTP_OC_OpenSession, intArrayOf(1))) {
                Log.w(TAG, "OpenSession failed")
                return false
            }
            operationNoData(PTP_OC_GetDeviceInfo, intArrayOf())
            operationNoData(PTP_OC_GetStorageIDs, intArrayOf())

            // Sony SDIO 3-phase handshake -- exact sequence confirmed
            // against alpha-fairy's real-device-tested init_table (see
            // class doc comment). Getting this order/params wrong is the
            // most likely reason a real camera would refuse to hand over
            // control even though the base PTP-IP connection succeeded.
            if (!operationNoData(OC_SDIOConnect, intArrayOf(1, 0, 0))) {
                Log.w(TAG, "SDIOConnect phase 1 failed")
                return false
            }
            if (!operationNoData(OC_SDIOConnect, intArrayOf(2, 0, 0))) {
                Log.w(TAG, "SDIOConnect phase 2 failed")
                return false
            }
            operationNoData(OC_SDIOGetExtDeviceInfo, intArrayOf(SDI_VERSION_V3, 0, 0))
            if (!operationNoData(OC_SDIOConnect, intArrayOf(3, 0, 0))) {
                Log.w(TAG, "SDIOConnect phase 3 failed")
                return false
            }
            operationNoData(OC_SDIOGetExtDeviceInfo, intArrayOf(SDI_VERSION_V3, 0, 0))

            isConnected = true
            Log.i(TAG, "Sony PTP-IP handshake complete on $ip")
            return true
        } catch (e: Exception) {
            Log.w(TAG, "Connect to $ip failed: ${e.message}")
            return false
        }
    }

    fun disconnect() {
        isConnected = false
        eventThreadRunning = false
        try { controlSocket?.close() } catch (_: Exception) {}
        try { eventSocket?.close() } catch (_: Exception) {}
        controlSocket = null; eventSocket = null
        controlIn = null; controlOut = null; eventIn = null
        connectedIp = null
    }

    // ---- High-level camera actions -------------------------------------

    /** Half-press (AF) + settle + full-press (capture), matching the real
     * two-stage shutter alpha-fairy's cmd_Shoot() uses -- confirmed
     * necessary because a lone full-press with no prior half-press often
     * fails to autofocus first on real Sony bodies. */
    fun triggerShutter(afSettleMs: Long = 700L, holdMs: Long = 120L): Boolean {
        if (!setControlDeviceB(PROP_AutoFocus, 2)) return false
        Thread.sleep(afSettleMs)
        val pressed = setControlDeviceB(PROP_Capture, 2)
        Thread.sleep(holdMs)
        val released = setControlDeviceB(PROP_Capture, 1)
        setControlDeviceB(PROP_AutoFocus, 1)
        return pressed && released
    }

    /** Drives the zoom motor toward TELE (positive step count moves out)
     * or WIDE for durationMs, then stops. This is a repeated-step command,
     * not a single absolute set, since ZoomStep is a momentary nudge per
     * alpha-fairy's cmd_ZoomStep -- exact step magnitude/cadence needed for
     * a smooth continuous zoom on this specific lens is unverified until
     * tested live. */
    fun driveZoom(tele: Boolean, durationMs: Long, stepIntervalMs: Long = 120L) {
        val step = if (tele) ZOOM_TELE_STEP else ZOOM_WIDE_STEP
        val deadline = System.currentTimeMillis() + durationMs
        while (System.currentTimeMillis() < deadline && isConnected) {
            setControlDeviceB(PROP_ZoomStep, step.toInt())
            Thread.sleep(stepIntervalMs)
        }
    }

    fun setIso(value: Int): Boolean = setControlDeviceA(PROP_ISO, value, 4)
    fun setWhiteBalance(value: Int): Boolean = setControlDeviceA(PROP_WhiteBalance, value, 2)
    fun setFocusMode(value: Int): Boolean = setControlDeviceA(PROP_FocusMode, value, 2)
    fun setExposureCompensation(value: Int): Boolean = setControlDeviceA(PROP_ExposureCompensation, value, 2)

    /** Fetches one live-view JPEG frame via GetObject on Sony's fixed
     * live-view pseudo-handle. Frame body format (an internal ~8-byte
     * status header before the raw JPEG bytes on most Sony bodies) is
     * NOT yet verified against a real ZV-E10 II response -- this returns
     * the raw object payload as-is; a live capture is needed to confirm
     * whether/where to strip a header before handing bytes to a JPEG
     * decoder. */
    fun fetchLiveViewFrameRaw(): ByteArray? {
        if (!isConnected) return null
        return try {
            sendOperationRequest(PTP_OC_GetObject, intArrayOf(LIVEVIEW_OBJECT_HANDLE))
            readDataPhase()
        } catch (e: Exception) {
            Log.w(TAG, "Live view fetch failed: ${e.message}")
            null
        }
    }

    // ---- Low-level PTP-IP framing ---------------------------------------

    private fun setControlDeviceA(propCode: Int, value: Int, byteWidth: Int): Boolean {
        if (!isConnected) return false
        val payload = ByteBuffer.allocate(byteWidth).order(ByteOrder.LITTLE_ENDIAN)
        when (byteWidth) {
            1 -> payload.put(value.toByte())
            2 -> payload.putShort(value.toShort())
            4 -> payload.putInt(value)
        }
        return operationWithData(OC_SetControlDeviceA, intArrayOf(propCode), payload.array())
    }

    private fun setControlDeviceB(propCode: Int, value: Int): Boolean {
        if (!isConnected) return false
        val payload = ByteBuffer.allocate(2).order(ByteOrder.LITTLE_ENDIAN).putShort(value.toShort()).array()
        return operationWithData(OC_SetControlDeviceB, intArrayOf(propCode), payload)
    }

    private fun operationNoData(opcode: Int, params: IntArray): Boolean {
        sendOperationRequest(opcode, params)
        return readOperationResponse()
    }

    private fun operationWithData(opcode: Int, params: IntArray, data: ByteArray): Boolean {
        sendOperationRequest(opcode, params)
        sendDataPhase(data)
        return readOperationResponse()
    }

    private fun sendInitCommandRequest(guid: ByteArray, name: String) {
        val nameBytes = utf16leNullTerminated(name)
        val body = ByteBuffer.allocate(guid.size + nameBytes.size).order(ByteOrder.LITTLE_ENDIAN)
        body.put(guid); body.put(nameBytes)
        writePacket(controlOut!!, PKT_INIT_COMMAND_REQUEST, body.array())
    }

    private fun readInitCommandAck(): Pair<Int, Int>? {
        val input = controlIn ?: return null
        val length = input.readIntLe()
        val type = input.readIntLe()
        val body = ByteArray(length - 8)
        input.readFully(body)
        if (type != PKT_INIT_COMMAND_ACK) return type to 0
        val connId = ByteBuffer.wrap(body, 0, 4).order(ByteOrder.LITTLE_ENDIAN).int
        return type to connId
    }

    private fun sendInitEventRequest(out: DataOutputStream, connId: Int) {
        val body = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(connId).array()
        writePacket(out, PKT_INIT_EVENT_REQUEST, body)
    }

    private fun readPacketType(input: DataInputStream): Int {
        val length = input.readIntLe()
        val type = input.readIntLe()
        val body = ByteArray(length - 8)
        input.readFully(body)
        return type
    }

    private fun sendOperationRequest(opcode: Int, params: IntArray) {
        val txId = transactionId.getAndIncrement()
        val body = ByteBuffer.allocate(8 + params.size * 4).order(ByteOrder.LITTLE_ENDIAN)
        body.putInt(0) // data phase info: 0 = no data / vendor-defined, matches alpha-fairy usage
        body.putShort(opcode.toShort()); body.putShort(0)
        body.putInt(txId)
        for (p in params) body.putInt(p)
        writePacket(controlOut!!, PKT_OPERATION_REQUEST, body.array())
    }

    private fun sendDataPhase(data: ByteArray) {
        val txId = transactionId.get() - 1
        val startBody = ByteBuffer.allocate(12).order(ByteOrder.LITTLE_ENDIAN)
        startBody.putInt(txId); startBody.putLong(data.size.toLong())
        writePacket(controlOut!!, PKT_START_DATA_PACKET, startBody.array())

        val dataBody = ByteBuffer.allocate(4 + data.size).order(ByteOrder.LITTLE_ENDIAN)
        dataBody.putInt(txId); dataBody.put(data)
        writePacket(controlOut!!, PKT_DATA_PACKET, dataBody.array())

        val endBody = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(txId).array()
        writePacket(controlOut!!, PKT_END_DATA_PACKET, endBody)
    }

    private fun readDataPhase(): ByteArray? {
        val input = controlIn ?: return null
        val out = java.io.ByteArrayOutputStream()
        while (true) {
            val length = input.readIntLe()
            val type = input.readIntLe()
            val body = ByteArray(length - 8)
            input.readFully(body)
            when (type) {
                PKT_START_DATA_PACKET -> { /* total length prefix, skip */ }
                PKT_DATA_PACKET -> out.write(body, 4, body.size - 4) // skip leading txId
                PKT_END_DATA_PACKET -> return out.toByteArray()
                PKT_OPERATION_RESPONSE -> return if (out.size() > 0) out.toByteArray() else null
                else -> Log.w(TAG, "Unexpected packet type $type during data phase")
            }
        }
    }

    private fun readOperationResponse(): Boolean {
        val input = controlIn ?: return false
        while (true) {
            val length = input.readIntLe()
            val type = input.readIntLe()
            val body = ByteArray(length - 8)
            input.readFully(body)
            when (type) {
                PKT_OPERATION_RESPONSE -> {
                    val code = ByteBuffer.wrap(body, 0, 2).order(ByteOrder.LITTLE_ENDIAN).short.toInt() and 0xFFFF
                    return code == 0x2001 // PTP_RC_OK
                }
                PKT_START_DATA_PACKET, PKT_DATA_PACKET, PKT_END_DATA_PACKET -> { /* drain, no data expected here */ }
                else -> Log.w(TAG, "Unexpected packet type $type waiting for operation response")
            }
        }
    }

    private fun writePacket(out: DataOutputStream, type: Int, body: ByteArray) {
        val header = ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN)
        header.putInt(8 + body.size); header.putInt(type)
        out.write(header.array())
        out.write(body)
        out.flush()
    }

    private fun DataInputStream.readIntLe(): Int {
        val b = ByteArray(4)
        readFully(b)
        return ByteBuffer.wrap(b).order(ByteOrder.LITTLE_ENDIAN).int
    }

    private fun startEventReaderThread() {
        val input = eventIn ?: return
        eventThreadRunning = true
        thread(name = "SonyPtpIpEventReader", isDaemon = true) {
            try {
                while (eventThreadRunning) {
                    val length = input.readIntLe()
                    val type = input.readIntLe()
                    val body = ByteArray(length - 8)
                    input.readFully(body)
                    if (type == PKT_EVENT) eventQueue.offer(body)
                }
            } catch (e: Exception) {
                if (eventThreadRunning) Log.w(TAG, "Event reader stopped: ${e.message}")
            }
        }
    }

    /** Blocks briefly waiting for the next camera-initiated event (e.g.
     * PropertyChanged, ObjectAdded when a photo finishes saving) -- returns
     * null on timeout. */
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
