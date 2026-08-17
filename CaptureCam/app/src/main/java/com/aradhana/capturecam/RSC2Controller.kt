package com.aradhana.capturecam

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import androidx.core.content.ContextCompat
import java.util.UUID

/**
 * Production-facing wrapper around the RSC 2 BLE control channel validated
 * in BleDiagnosticsActivity -- same protocol (DumlProtocol), same target
 * characteristic (FFF5, discovered by UUID rather than hardcoding an ATT
 * handle since handle numbers aren't guaranteed stable across firmware/
 * connections). This is the one motion-control entry point the capture
 * pipeline should use; anything that needs to move the gimbal goes through
 * here, not through ad-hoc BLE calls elsewhere.
 *
 * Axis mapping confirmed on real hardware (2026-08-17, isolated one-axis-
 * at-a-time tests via the ADB test-move broadcast -- see MainActivity's
 * testMoveReceiver):
 *   axis1 = TILT (pitch, up/down) -- deflection above center = look up
 *   axis2 = ROLL (rotates the frame landscape <-> vertical) -- not used by
 *           the production capture sequence, keep at center or framing rotates
 *   axis3 = PAN (yaw, left/right) -- what the 3-angle sweep uses
 * All three center at DumlProtocol.AXIS_CENTER (1024). This mapping held
 * for this specific physical mount/orientation; if the gimbal is ever
 * mounted differently, re-verify with the same one-axis-at-a-time method
 * rather than assuming it still holds.
 */
class RSC2Controller {

    companion object {
        private const val TAG = "RSC2Controller"
        private val SERVICE_UUID: UUID = UUID.fromString("0000fff0-0000-1000-8000-00805f9b34fb")
        private val COMMAND_CHAR_UUID: UUID = UUID.fromString("0000fff5-0000-1000-8000-00805f9b34fb")
    }

    private val handler = Handler(Looper.getMainLooper())
    private var gatt: BluetoothGatt? = null
    private var commandCharacteristic: BluetoothGattCharacteristic? = null
    private var seq = 1
    private var activeMoveRunnable: Runnable? = null
    private var heartbeatRunnable: Runnable? = null

    val isReady: Boolean get() = commandCharacteristic != null && gatt != null

    /**
     * The captured Ronin-app BLE traffic never went quiet -- it sent SOME
     * frame roughly once a second for the whole session, including while
     * completely idle. A neutral-joystick-only heartbeat was NOT enough:
     * live testing showed the RSC 2 still dropping the connection ~15-25s
     * after the last real joystick activity even with that running. The
     * real app was also continuously sending ping frames to several OTHER
     * receiver IDs (0x04/0xbf/0xdf) plus a status-report frame (0xe5) the
     * whole time -- cycling through all of them here since it's not known
     * which one the RSC 2 actually requires to consider the session alive.
     */
    private fun startHeartbeat() {
        stopHeartbeat()
        var tick = 0
        val runnable = object : Runnable {
            override fun run() {
                if (isReady && activeMoveRunnable == null) {
                    val frame = when (tick % 4) {
                        0 -> DumlProtocol.neutralFrame(seq)
                        1 -> DumlProtocol.pingFrame(DumlProtocol.PING_RECEIVERS[0], seq)
                        2 -> DumlProtocol.pingFrame(DumlProtocol.PING_RECEIVERS[1], seq)
                        else -> DumlProtocol.statusReportFrame(seq)
                    }
                    writeFrame(frame); seq += 1
                    tick += 1
                }
                handler.postDelayed(this, 900L)
            }
        }
        heartbeatRunnable = runnable
        handler.postDelayed(runnable, 900L)
    }

    private fun stopHeartbeat() {
        heartbeatRunnable?.let { handler.removeCallbacks(it) }
        heartbeatRunnable = null
    }

    private fun hasPermission(context: Context, permission: String): Boolean =
        ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED

    private fun hasBlePermissions(context: Context): Boolean {
        return if (Build.VERSION.SDK_INT >= 31) {
            hasPermission(context, Manifest.permission.BLUETOOTH_SCAN) &&
                hasPermission(context, Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            hasPermission(context, Manifest.permission.ACCESS_FINE_LOCATION)
        }
    }

    /**
     * Scans for a device whose advertised name contains "RSC" (case
     * insensitive) and connects to it. Calls onResult(true) once FFF5 is
     * found and ready to accept commands, onResult(false) on any failure
     * (permissions, no device found, Bluetooth off, GATT error) -- always
     * fails open to the caller rather than throwing, since the capture
     * pipeline must keep working in single-image mode when no gimbal is
     * present (spec rule 61).
     */
    fun connect(context: Context, scanTimeoutMs: Long = 10_000L, onResult: (Boolean) -> Unit) {
        if (!hasBlePermissions(context)) {
            Log.w(TAG, "Missing BLE permissions -- cannot connect to RSC 2")
            onResult(false)
            return
        }
        val adapter = (context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager).adapter
        if (adapter == null || !adapter.isEnabled) {
            Log.w(TAG, "Bluetooth unavailable or off")
            onResult(false)
            return
        }

        var resolved = false
        fun finish(success: Boolean) {
            if (resolved) return
            resolved = true
            onResult(success)
        }

        val scanCallback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                val name = try { result.device.name } catch (e: SecurityException) { null } ?: return
                if (!name.contains("RSC", ignoreCase = true) && !name.contains("Ronin", ignoreCase = true)) return
                try {
                    adapter.bluetoothLeScanner?.stopScan(this)
                } catch (_: SecurityException) {}
                connectToDevice(context, result.device) { finish(it) }
            }

            override fun onScanFailed(errorCode: Int) {
                Log.w(TAG, "Scan failed: $errorCode")
                finish(false)
            }
        }

        try {
            adapter.bluetoothLeScanner?.startScan(scanCallback)
        } catch (e: SecurityException) {
            Log.w(TAG, "Missing permission to scan: ${e.message}")
            finish(false)
            return
        }
        handler.postDelayed({
            if (!resolved) {
                try { adapter.bluetoothLeScanner?.stopScan(scanCallback) } catch (_: SecurityException) {}
                Log.w(TAG, "Scan timed out -- no RSC 2 found")
                finish(false)
            }
        }, scanTimeoutMs)
    }

    private fun connectToDevice(context: Context, device: BluetoothDevice, onResult: (Boolean) -> Unit) {
        var resolved = false
        fun finish(success: Boolean) {
            if (resolved) return
            resolved = true
            onResult(success)
        }
        val callback = object : BluetoothGattCallback() {
            override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
                if (newState == BluetoothProfile.STATE_CONNECTED) {
                    try { g.discoverServices() } catch (e: SecurityException) { finish(false) }
                } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                    Log.w(TAG, "RSC 2 disconnected (status=$status)")
                    commandCharacteristic = null
                    stopHeartbeat()
                    if (!resolved) finish(false)
                }
            }

            override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
                val service = g.getService(SERVICE_UUID)
                val char = service?.getCharacteristic(COMMAND_CHAR_UUID)
                commandCharacteristic = char
                if (char != null) {
                    Log.i(TAG, "RSC 2 ready -- command channel found")
                    startHeartbeat()
                }
                finish(char != null)
            }
        }
        try {
            gatt = device.connectGatt(context, false, callback)
        } catch (e: SecurityException) {
            Log.w(TAG, "Missing permission to connect: ${e.message}")
            finish(false)
        }
        handler.postDelayed({ if (!resolved) finish(false) }, 8_000L)
    }

    @Suppress("DEPRECATION")
    private fun writeFrame(frame: ByteArray) {
        val char = commandCharacteristic
        val g = gatt
        if (char == null || g == null) {
            Log.w(TAG, "writeFrame: no-op, char=$char gatt=$g")
            return
        }
        try {
            // The old characteristic.value=/writeCharacteristic(characteristic)
            // pair (API <33) was returning false on essentially every call on
            // this device/stack, even with 900ms between idle heartbeats --
            // not a pacing issue, a real reliability problem with the
            // deprecated API. The API 33+ writeCharacteristic(char, value,
            // writeType) overload is Android's own fix for exactly this.
            val ok = if (Build.VERSION.SDK_INT >= 33) {
                val result = g.writeCharacteristic(char, frame, BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE)
                result == android.bluetooth.BluetoothStatusCodes.SUCCESS
            } else {
                char.writeType = BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
                char.value = frame
                g.writeCharacteristic(char)
            }
            if (!ok) Log.w(TAG, "writeCharacteristic() failed (sdk=${Build.VERSION.SDK_INT})")
        } catch (e: SecurityException) {
            Log.w(TAG, "Missing permission to write: ${e.message}")
        }
    }

    /**
     * These are joystick/velocity commands, not absolute-position commands
     * -- confirmed the hard way: sending "neutral" after a deflected move
     * only STOPS further movement, it does not undo the deflection that
     * already happened. The gimbal never returned to the true MAIN/home
     * position between items, so item 2's "same" angle offsets landed on an
     * already-drifted position. moveOut()/returnHome() are a matched pair:
     * moveOut deflects for durationMs then stops (for the capture), and the
     * caller MUST call returnHome with the same axis values afterward,
     * which deflects in the mirrored direction for the same duration to
     * physically undo the move, then stops again. Every call site in
     * MainActivity's angle sequence must pair these, or drift returns.
     */
    private fun streamDeflection(axis1: Int, axis2: Int, axis3: Int, durationMs: Long, settleMs: Long, onDone: () -> Unit) {
        activeMoveRunnable?.let { handler.removeCallbacks(it) }
        if (!isReady) {
            Log.w(TAG, "streamDeflection($axis1,$axis2,$axis3): not ready (char=$commandCharacteristic gatt=$gatt) -- skipping")
            onDone()
            return
        }
        Log.i(TAG, "streamDeflection($axis1,$axis2,$axis3) starting")
        val ticks = (durationMs / 200L).toInt().coerceAtLeast(1)
        var sent = 0
        val runnable = object : Runnable {
            override fun run() {
                if (sent >= ticks) {
                    val stopFrame = DumlProtocol.neutralFrame(seq); seq += 1
                    writeFrame(stopFrame)
                    activeMoveRunnable = null
                    handler.postDelayed(onDone, settleMs)
                    return
                }
                val frame = DumlProtocol.buildJoystickFrame(axis1, axis2, axis3, seq)
                seq += 1
                writeFrame(frame)
                sent += 1
                handler.postDelayed(this, 200L)
            }
        }
        activeMoveRunnable = runnable
        handler.post(runnable)
    }

    /** Deflects toward (axis1, axis2, axis3) and stops there -- call
     * returnHome with the SAME values afterward to physically undo this
     * move. Any axis left at DumlProtocol.AXIS_CENTER doesn't move. */
    fun moveOut(
        axis1: Int = DumlProtocol.AXIS_CENTER, axis2: Int = DumlProtocol.AXIS_CENTER,
        axis3: Int = DumlProtocol.AXIS_CENTER, durationMs: Long = 900L, settleMs: Long = 400L,
        onArrived: () -> Unit
    ) {
        streamDeflection(axis1, axis2, axis3, durationMs, settleMs, onArrived)
    }

    /** Mirrors (axis1, axis2, axis3) around center and deflects that
     * direction for the same duration, physically undoing a matching
     * moveOut() call. */
    fun returnHome(
        axis1: Int = DumlProtocol.AXIS_CENTER, axis2: Int = DumlProtocol.AXIS_CENTER,
        axis3: Int = DumlProtocol.AXIS_CENTER, durationMs: Long = 900L, settleMs: Long = 400L,
        onReturned: () -> Unit
    ) {
        val mirrored1 = 2 * DumlProtocol.AXIS_CENTER - axis1
        val mirrored2 = 2 * DumlProtocol.AXIS_CENTER - axis2
        val mirrored3 = 2 * DumlProtocol.AXIS_CENTER - axis3
        streamDeflection(mirrored1, mirrored2, mirrored3, durationMs, settleMs, onReturned)
    }

    fun stopAndReturnToCenter() {
        activeMoveRunnable?.let { handler.removeCallbacks(it) }
        activeMoveRunnable = null
        if (isReady) {
            val frame = DumlProtocol.neutralFrame(seq); seq += 1
            writeFrame(frame)
        }
    }

    fun disconnect() {
        stopHeartbeat()
        activeMoveRunnable?.let { handler.removeCallbacks(it) }
        activeMoveRunnable = null
        try {
            gatt?.disconnect()
            gatt?.close()
        } catch (_: SecurityException) {}
        gatt = null
        commandCharacteristic = null
    }
}
