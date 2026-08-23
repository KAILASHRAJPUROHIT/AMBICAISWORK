package com.aradhana.capturecam

import android.util.Log
import com.jcraft.jsch.Channel
import com.jcraft.jsch.ChannelDirectTCPIP
import com.jcraft.jsch.JSch
import com.jcraft.jsch.Session
import java.io.InputStream
import java.io.OutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlin.concurrent.thread

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

        // --- Standard PTP opcodes ---
        private const val PTP_OC_GetDeviceInfo = 0x1001
        private const val PTP_OC_OpenSession = 0x1002
        private const val PTP_OC_GetStorageIDs = 0x1004
        private const val PTP_OC_GetObject = 0x1009

        // --- Sony SDIO extension opcodes (reverse engineered, see class doc) ---
        private const val OC_SDIOConnect = 0x9201
        private const val OC_SDIOGetExtDeviceInfo = 0x9202
        private const val OC_SetControlDeviceA = 0x9205
        private const val OC_SetControlDeviceB = 0x9207

        const val PROP_AutoFocus = 0xD2C1        // S1 (half-press) -- 2=engage, 1=release
        const val PROP_Capture = 0xD2C2          // S2 (full-press) -- 2=engage, 1=release
        const val PROP_ISO = 0xD21E
        const val PROP_WhiteBalance = 0x5005
        const val PROP_FocusMode = 0x500A
        const val PROP_ZoomStep = 0xD2DD         // signed step; sign = direction
        const val PROP_ExposureCompensation = 0x5010

        const val ZOOM_TELE_STEP: Short = -1
        const val ZOOM_WIDE_STEP: Short = 1

        private const val SDI_VERSION_V3 = 0x012C // 300 -- matches pysonycam's SDI_VERSION_V3
        private const val LIVEVIEW_OBJECT_HANDLE = 0xFFFFC002.toInt()
    }

    private var sshSession: Session? = null
    private var controlChannel: ChannelDirectTCPIP? = null
    private var eventChannel: ChannelDirectTCPIP? = null
    private var controlOut: OutputStream? = null
    private var controlIn: InputStream? = null
    private var eventIn: InputStream? = null
    private val transactionId = AtomicInteger(1)
    private val eventQueue = LinkedBlockingQueue<ByteArray>()
    @Volatile private var eventThreadRunning = false

    @Volatile var isConnected: Boolean = false
        private set

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
        try {
            val jsch = JSch()
            val session = jsch.getSession(sshUser, cameraIp, 22)
            session.setPassword(sshPassword)
            // The camera's SSH host key changes per-device and isn't
            // something an operator can pre-provision -- same trust model
            // as the original PTP-IP GUID pairing this replaces (trust on
            // first use, on a LAN the operator physically controls).
            session.setConfig("StrictHostKeyChecking", "no")
            session.timeout = timeoutMs
            session.connect(timeoutMs)
            sshSession = session
            Log.i(TAG, "SSH authenticated to $cameraIp as $sshUser")

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
            eventIn = evt.inputStream
            sendInitEventRequest(evt.outputStream, connId)
            val eventAckType = readPacketType(eventIn!!)
            if (eventAckType != PKT_INIT_EVENT_ACK) {
                Log.w(TAG, "Expected Init Event Ack, got type $eventAckType")
                return false
            }

            startEventReaderThread()

            // Restored -- removing this did NOT fix the SessionNotOpen
            // errors on GetDeviceInfo/SDIOConnect (confirmed live: identical
            // failure with or without it), so the earlier theory that
            // alpha-fairy's init_table implies no OpenSession was wrong --
            // its own connection writeup separately documents OpenSession
            // as its own step BEFORE those init_table substeps run.
            Log.i(TAG, "OpenSession result: ${operationNoData(PTP_OC_OpenSession, intArrayOf(1))}")
            Log.i(TAG, "GetDeviceInfo result: ${operationNoData(PTP_OC_GetDeviceInfo, intArrayOf())}")
            Log.i(TAG, "GetStorageIDs result: ${operationNoData(PTP_OC_GetStorageIDs, intArrayOf())}")

            // Sony SDIO 3-phase handshake -- confirmed sequence against
            // alpha-fairy's real-device-tested init_table (see class doc).
            if (!operationNoData(OC_SDIOConnect, intArrayOf(1, 0, 0))) {
                Log.w(TAG, "SDIOConnect phase 1 failed"); return false
            }
            if (!operationNoData(OC_SDIOConnect, intArrayOf(2, 0, 0))) {
                Log.w(TAG, "SDIOConnect phase 2 failed"); return false
            }
            operationNoData(OC_SDIOGetExtDeviceInfo, intArrayOf(SDI_VERSION_V3, 0, 0))
            if (!operationNoData(OC_SDIOConnect, intArrayOf(3, 0, 0))) {
                Log.w(TAG, "SDIOConnect phase 3 failed"); return false
            }
            operationNoData(OC_SDIOGetExtDeviceInfo, intArrayOf(SDI_VERSION_V3, 0, 0))

            isConnected = true
            Log.i(TAG, "Sony PTP-IP-over-SSH handshake complete")
            return true
        } catch (e: Exception) {
            Log.w(TAG, "Connect failed: ${e.message}", e)
            return false
        }
    }

    private fun openTunnelChannel(session: Session, timeoutMs: Int): ChannelDirectTCPIP? {
        return try {
            val channel = session.openChannel("direct-tcpip") as ChannelDirectTCPIP
            channel.setHost(TUNNEL_HOST)
            channel.setPort(TUNNEL_PORT)
            channel.connect(timeoutMs)
            channel
        } catch (e: Exception) {
            Log.w(TAG, "openTunnelChannel failed: ${e.message}")
            null
        }
    }

    fun disconnect() {
        isConnected = false
        eventThreadRunning = false
        try { controlChannel?.disconnect() } catch (_: Exception) {}
        try { eventChannel?.disconnect() } catch (_: Exception) {}
        try { sshSession?.disconnect() } catch (_: Exception) {}
        sshSession = null; controlChannel = null; eventChannel = null
        controlIn = null; controlOut = null; eventIn = null
    }

    // ---- High-level camera actions -------------------------------------

    fun triggerShutter(afSettleMs: Long = 700L, holdMs: Long = 120L): Boolean {
        if (!setControlDeviceB(PROP_AutoFocus, 2)) return false
        Thread.sleep(afSettleMs)
        val pressed = setControlDeviceB(PROP_Capture, 2)
        Thread.sleep(holdMs)
        val released = setControlDeviceB(PROP_Capture, 1)
        setControlDeviceB(PROP_AutoFocus, 1)
        return pressed && released
    }

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

    // ---- Low-level PTP-IP framing (over the SSH-tunneled channel) ------

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

    private fun sendOperationRequest(opcode: Int, params: IntArray) {
        val txId = transactionId.getAndIncrement()
        // dataphase(4) + opcode(2) + reserved(2) + txId(4) = 12 fixed bytes,
        // not 8 -- an earlier undersized allocation here threw
        // BufferOverflowException on the very first real operation request
        // (OpenSession) once the handshake up to this point started
        // working for real against the camera.
        val body = ByteBuffer.allocate(12 + params.size * 4).order(ByteOrder.LITTLE_ENDIAN)
        body.putInt(0)
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
            readFullyFrom(input, body)
            when (type) {
                PKT_START_DATA_PACKET -> { /* total length prefix, skip */ }
                PKT_DATA_PACKET -> out.write(body, 4, body.size - 4)
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
            readFullyFrom(input, body)
            when (type) {
                PKT_OPERATION_RESPONSE -> {
                    val code = ByteBuffer.wrap(body, 0, 2).order(ByteOrder.LITTLE_ENDIAN).short.toInt() and 0xFFFF
                    if (code != 0x2001) Log.w(TAG, "Operation response code: 0x${code.toString(16)} (not OK)")
                    return code == 0x2001 // PTP_RC_OK
                }
                PKT_START_DATA_PACKET, PKT_DATA_PACKET, PKT_END_DATA_PACKET -> { /* drain, no data expected here */ }
                else -> Log.w(TAG, "Unexpected packet type $type waiting for operation response")
            }
        }
    }

    private fun writePacket(out: OutputStream, type: Int, body: ByteArray) {
        val header = ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN)
        header.putInt(8 + body.size); header.putInt(type)
        out.write(header.array())
        out.write(body)
        out.flush()
    }

    private fun InputStream.readIntLe(): Int {
        val b = ByteArray(4)
        readFullyFrom(this, b)
        return ByteBuffer.wrap(b).order(ByteOrder.LITTLE_ENDIAN).int
    }

    private fun readFullyFrom(input: InputStream, buf: ByteArray) {
        var offset = 0
        while (offset < buf.size) {
            val n = input.read(buf, offset, buf.size - offset)
            if (n < 0) throw java.io.EOFException("Stream closed after $offset/${buf.size} bytes")
            offset += n
        }
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
                    readFullyFrom(input, body)
                    if (type == PKT_EVENT) eventQueue.offer(body)
                }
            } catch (e: Exception) {
                if (eventThreadRunning) Log.w(TAG, "Event reader stopped: ${e.message}")
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
