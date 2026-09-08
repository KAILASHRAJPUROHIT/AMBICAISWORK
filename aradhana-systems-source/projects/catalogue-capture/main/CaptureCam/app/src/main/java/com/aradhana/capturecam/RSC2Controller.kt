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
    @Volatile private var activeMoveRunnable: Runnable? = null
    private var heartbeatRunnable: Runnable? = null
    @Volatile private var connectInFlight = false

    val isReady: Boolean get() = commandCharacteristic != null && gatt != null

    /**
     * Fires when the gimbal disconnects AFTER a successful connect() --
     * i.e. mid-session, not a failed initial connection attempt (that path
     * already reports through connect()'s own onResult(false)). Confirmed
     * live (2026-08-23): once connect() has succeeded once, MainActivity's
     * self-heal retry loop (scheduleGimbalRetry/attemptGimbalConnect)
     * terminates permanently -- it only re-triggers on onCreate/onResume/
     * onNewIntent, never from inside a long-running foreground session. A
     * later real BLE drop (range, RF interference, OS stack hiccup -- all
     * normal for a BLE peripheral) was therefore never retried until the
     * Activity happened to pause/resume for some unrelated reason (e.g.
     * navigating to BLE Diagnostics and back), which read from the
     * operator's side as the gimbal being permanently dead until an app
     * restart. Set this to route unexpected disconnects back into the same
     * retry loop the initial connect uses. */
    var onUnexpectedDisconnect: (() -> Unit)? = null

    /** True while a moveOut()/returnHome() burst is actively streaming
     * frames (i.e. the gimbal is physically in motion or settling from
     * one) -- false once its onDone/onArrived/onReturned callback fires.
     * The capture pipeline must never evaluate "ready to shoot" while this
     * is true: tracking during motion is for framing/focus follow only. */
    val isMoving: Boolean get() = activeMoveRunnable != null

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
        if (isReady) {
            onResult(true)
            return
        }
        if (connectInFlight) {
            Log.d(TAG, "RSC 2 connect already in flight")
            return
        }
        connectInFlight = true
        if (!hasBlePermissions(context)) {
            Log.w(TAG, "Missing BLE permissions -- cannot connect to RSC 2")
            connectInFlight = false
            onResult(false)
            return
        }
        val adapter = (context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager).adapter
        if (adapter == null || !adapter.isEnabled) {
            Log.w(TAG, "Bluetooth unavailable or off")
            connectInFlight = false
            onResult(false)
            return
        }

        var resolved = false
        fun finish(success: Boolean) {
            if (resolved) return
            resolved = true
            connectInFlight = false
            onResult(success)
        }

        var deviceConnectStarted = false
        val scanCallback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                if (deviceConnectStarted) return
                val name = try { result.device.name } catch (e: SecurityException) { null } ?: return
                if (!name.contains("RSC", ignoreCase = true) && !name.contains("Ronin", ignoreCase = true)) return
                deviceConnectStarted = true
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
                    // Always close/clear the GATT client here, not just on
                    // an explicit disconnect() call -- otherwise every
                    // unexpected drop-and-reconnect cycle leaks a stale
                    // BluetoothGatt object (connectGatt() is called again
                    // on the next attempt without this one ever being
                    // closed), which can exhaust the OS BLE stack's
                    // connection slots over a long session.
                    try { g.close() } catch (_: SecurityException) {}
                    if (gatt === g) gatt = null
                    commandCharacteristic = null
                    stopHeartbeat()
                    if (!resolved) {
                        finish(false)
                    } else {
                        onUnexpectedDisconnect?.invoke()
                    }
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

            override fun onCharacteristicWrite(
                g: BluetoothGatt,
                characteristic: BluetoothGattCharacteristic,
                status: Int
            ) {
                if (characteristic.uuid != COMMAND_CHAR_UUID) return
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    Log.d(TAG, "RSC 2 write confirmed")
                } else {
                    Log.w(TAG, "RSC 2 write callback failed status=$status")
                }
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
            // This tablet's Android 16 vendor stack has returned a non-zero
            // queue result while still delivering onCharacteristicWrite(0).
            // Treat the callback as authoritative; keep this as diagnostic
            // detail instead of a false production failure every 900 ms.
            if (!ok) Log.d(TAG, "RSC 2 write queue returned non-success (sdk=${Build.VERSION.SDK_INT})")
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
        // Velocity ramp, not an instant on/off step -- per explicit request
        // (2026-08-18): every frame before this held FULL deflection for
        // every tick, then snapped straight back to AXIS_CENTER on the
        // final tick. That's a true step function (0 -> full -> 0
        // instantly), which is exactly what reads as a jerky start/stop
        // jolt on a physical gimbal. The 200ms per-frame cadence itself is
        // a real BLE constraint confirmed earlier this session (this
        // protocol has no sub-200ms frame rate established as safe), so
        // this doesn't change WHEN frames go out, only ramps each axis's
        // MAGNITUDE up over the first tick and back down over the last
        // tick (when there's room -- a single-tick burst has no ramp
        // headroom and stays full magnitude, unavoidable with only one
        // frame available). Full magnitude for the ticks in between keeps
        // net displacement close to the original calibrated duration-to-
        // motion mapping (centeringDurationFor()), so existing tuning
        // isn't invalidated -- only the edges are softened.
        val rampTicks = if (ticks >= 3) 1 else 0
        fun rampFraction(index: Int): Float = when {
            rampTicks == 0 -> 1f
            index < rampTicks -> (index + 1).toFloat() / (rampTicks + 1)
            index >= ticks - rampTicks -> (ticks - index).toFloat() / (rampTicks + 1)
            else -> 1f
        }
        fun scaledAxis(target: Int, fraction: Float): Int =
            (DumlProtocol.AXIS_CENTER + (target - DumlProtocol.AXIS_CENTER) * fraction).toInt()
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
                val fraction = rampFraction(sent)
                val frame = DumlProtocol.buildJoystickFrame(
                    scaledAxis(axis1, fraction), scaledAxis(axis2, fraction), scaledAxis(axis3, fraction), seq
                )
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
