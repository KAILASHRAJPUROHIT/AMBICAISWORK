package com.aradhana.capturecam

/**
 * DJI's DUML frame protocol, as used by the Ronin app to drive the RSC 2
 * over BLE (characteristic FFF5 for commands, FFF3/FFF4 for status/notify).
 * DJI publishes no developer SDK for the RSC 2 -- everything here was
 * derived by capturing the Ronin app's own real BLE traffic (Android's
 * Bluetooth HCI snoop log) and empirically verifying the checksum algorithm
 * against 507 real captured frames (100% match) rather than guessed.
 *
 * Frame layout (all multi-byte fields little-endian):
 *   [0]      SOF = 0x55
 *   [1]      LEN (total frame length, header+body+crc16)
 *   [2]      VER = 0x04 (constant in every captured frame)
 *   [3]      CRC8 over bytes[0:3]
 *   [4]      SENDER   (0x02 = mobile/host, in every captured command)
 *   [5]      RECEIVER (0x04 = the module that accepts joystick commands)
 *   [6:8]    SEQ (2 bytes LE) -- increments per frame sent; the real device
 *            did not appear to require strict continuity, but incrementing
 *            it matches observed behavior and avoids relying on that.
 *   [8]      CMD_TYPE = 0x40
 *   [9]      CMD_SET  = 0x04
 *   [10]     CMD_ID   = 0x01  (the joystick/pose command, per captured data)
 *   [11:20]  DATA (9 bytes): axis1(u16 LE), axis2(u16 LE), axis3(u16 LE),
 *            0x00, 0x00, 0x02 -- each axis centers at 1024; deflection
 *            above/below 1024 moves the gimbal, confirmed live on real
 *            hardware in both directions. Which axis maps to which of
 *            yaw/pitch/roll is NOT yet confirmed -- axis1 and axis3 were
 *            both observed varying during Ronin app joystick drags, axis2
 *            was never observed to move from 1024 in the captured session.
 *   [-2:]    CRC16 over bytes[0:-2], stored LE.
 */
object DumlProtocol {

    private const val SOF = 0x55
    private const val VERSION = 0x04
    const val AXIS_CENTER = 1024

    private fun crc8(data: ByteArray, init: Int = 0x77): Int {
        var reg = init
        for (b in data) {
            reg = reg xor (b.toInt() and 0xFF)
            repeat(8) {
                reg = if (reg and 1 != 0) (reg ushr 1) xor 0x8C else reg ushr 1
            }
        }
        return reg and 0xFF
    }

    private fun crc16(data: ByteArray, init: Int = 0x3692): Int {
        var reg = init
        for (b in data) {
            reg = reg xor (b.toInt() and 0xFF)
            repeat(8) {
                reg = if (reg and 1 != 0) (reg ushr 1) xor 0x8408 else reg ushr 1
            }
        }
        return reg and 0xFFFF
    }

    private fun u16le(value: Int): ByteArray {
        val v = value.coerceIn(0, 0xFFFF)
        return byteArrayOf((v and 0xFF).toByte(), ((v ushr 8) and 0xFF).toByte())
    }

    /** Generic frame builder -- every other builder in this file is a thin
     * wrapper over this with a fixed receiver/cmd_type/cmd_set/cmd_id/data. */
    fun buildFrame(receiver: Int, cmdType: Int, cmdSet: Int, cmdId: Int, data: ByteArray, seq: Int): ByteArray {
        val bodyAfterLenVer = byteArrayOf(
            0x02, receiver.toByte(),                      // sender, receiver
            (seq and 0xFF).toByte(), ((seq ushr 8) and 0xFF).toByte(), // seq LE
            cmdType.toByte(), cmdSet.toByte(), cmdId.toByte()
        ) + data
        val totalLen = 4 + bodyAfterLenVer.size + 2 // SOF+LEN+VER+CRC8 + body + CRC16
        val header = byteArrayOf(SOF.toByte(), totalLen.toByte(), VERSION.toByte())
        val crc8Value = crc8(header)
        val frameNoTrailer = header + byteArrayOf(crc8Value.toByte()) + bodyAfterLenVer
        val crc16Value = crc16(frameNoTrailer)
        return frameNoTrailer + u16le(crc16Value)
    }

    /**
     * Builds a valid, checksummed joystick/pose frame ready to write
     * directly to FFF5. axis1/axis2/axis3 are raw values centered on
     * AXIS_CENTER (1024) -- callers deflect away from center to command
     * movement, matching exactly what was observed from the real app.
     */
    fun buildJoystickFrame(axis1: Int, axis2: Int, axis3: Int, seq: Int): ByteArray {
        val data = u16le(axis1) + u16le(axis2) + u16le(axis3) + byteArrayOf(0x00, 0x00, 0x02)
        return buildFrame(receiver = 0x04, cmdType = 0x40, cmdSet = 0x04, cmdId = 0x01, data = data, seq = seq)
    }

    /** Neutral/center frame -- sending this stops movement. */
    fun neutralFrame(seq: Int): ByteArray = buildJoystickFrame(AXIS_CENTER, AXIS_CENTER, AXIS_CENTER, seq)

    /**
     * The Ronin app never actually stopped sending traffic, even fully
     * idle -- alongside (not instead of) joystick frames, it continuously
     * sent two OTHER message types about once a second each. Sending only
     * neutral joystick frames as a "heartbeat" was not enough: the RSC 2
     * still dropped the connection ~15-25s after the last real joystick
     * activity in live testing. These two replicate the actual observed
     * idle traffic instead of guessing at a third message type.
     */
    fun pingFrame(seq: Int): ByteArray =
        buildFrame(receiver = 0x04, cmdType = 0x40, cmdSet = 0x00, cmdId = 0x01, data = ByteArray(0), seq = seq)

    private val STATUS_REPORT_DATA = byteArrayOf(
        0x10, 0x51, 0x01, 0x00, 0x00, 0x00, 0x0c, 0x00, 0x00, 0x50,
        0x00, 0xf1.toByte(), 0x03, 0x66, 0x24, 0xc0.toByte(), 0x1d, 0x00, 0x00, 0x1c
    )
    fun statusReportFrame(seq: Int): ByteArray =
        buildFrame(receiver = 0xe5, cmdType = 0x00, cmdSet = 0x04, cmdId = 0x12, data = STATUS_REPORT_DATA, seq = seq)
}
