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
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

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
        if (results.values.all { it }) startScan() else log("Permissions denied -- cannot scan.")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_ble_diagnostics)

        statusText = findViewById(R.id.bleStatusText)
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

        log("Ready. Turn on the RSC 2, put it in Bluetooth pairing mode (per its manual), then tap Scan.")
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
        super.onDestroy()
        try {
            if (scanning) bluetoothAdapter.bluetoothLeScanner?.stopScan(scanCallback)
            gatt?.close()
        } catch (_: SecurityException) {}
    }
}
