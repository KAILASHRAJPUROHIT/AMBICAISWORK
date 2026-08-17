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
 * Axis mapping confirmed on real hardware (2026-08-17): axis1 = tilt
 * (up/down), axis2 = pan (left/right). axis3's effect is NOT confirmed --
 * avoid relying on it until it's characterized. All three center at
 * DumlProtocol.AXIS_CENTER (1024).
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
     * completely idle. A single item's move-capture-move-capture sequence
     * worked, then a subsequent item never moved at all, with no BLE
     * disconnect logged -- consistent with the RSC 2 treating a joystick
     * session as ended after a period of silence (the pause between items
     * while the operator repositions/scans the next tag). This keeps a
     * trickle of neutral frames going during any such pause so the session
     * the gimbal thinks is active actually stays active.
     */
    private fun startHeartbeat() {
        stopHeartbeat()
        val runnable = object : Runnable {
            override fun run() {
                if (isReady && activeMoveRunnable == null) {
                    writeFrame(DumlProtocol.neutralFrame(seq)); seq += 1
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
        char.writeType = BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
        char.value = frame
        try {
            val ok = g.writeCharacteristic(char)
            if (!ok) Log.w(TAG, "writeCharacteristic() returned false")
        } catch (e: SecurityException) {
            Log.w(TAG, "Missing permission to write: ${e.message}")
        }
    }

    /**
     * Moves toward (axis1, axis2) by streaming the deflected frame at the
     * same ~200ms cadence observed from the real Ronin app for
     * [durationMs], then returns to neutral. Calls onDone when the whole
     * sequence (including the settle time after returning to neutral) has
     * finished. axis3 is left at center -- see class doc, its effect isn't
     * confirmed yet.
     */
    fun moveTo(axis1: Int, axis2: Int, durationMs: Long = 900L, settleMs: Long = 500L, onDone: () -> Unit) {
        activeMoveRunnable?.let { handler.removeCallbacks(it) }
        if (!isReady) {
            Log.w(TAG, "moveTo($axis1,$axis2): not ready (char=$commandCharacteristic gatt=$gatt) -- skipping move")
            onDone()
            return
        }
        Log.i(TAG, "moveTo($axis1,$axis2) starting")
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
                val frame = DumlProtocol.buildJoystickFrame(axis1, axis2, DumlProtocol.AXIS_CENTER, seq)
                seq += 1
                writeFrame(frame)
                sent += 1
                handler.postDelayed(this, 200L)
            }
        }
        activeMoveRunnable = runnable
        handler.post(runnable)
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
