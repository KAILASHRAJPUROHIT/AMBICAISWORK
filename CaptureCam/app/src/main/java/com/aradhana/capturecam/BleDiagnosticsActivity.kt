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

    private val handler = Handler(Looper.getMainLooper())
    private val bluetoothAdapter by lazy {
        (getSystemService(BLUETOOTH_SERVICE) as BluetoothManager).adapter
    }
    private var gatt: BluetoothGatt? = null
    private var selectedCharacteristic: BluetoothGattCharacteristic? = null
    private val seenAddresses = mutableSetOf<String>()
    private var scanning = false

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

        findViewById<Button>(R.id.scanButton).setOnClickListener { requestPermissionsThenScan() }
        findViewById<Button>(R.id.disconnectButton).setOnClickListener { disconnect() }
        findViewById<Button>(R.id.sendBytesButton).setOnClickListener { sendHexToSelected() }

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
                }
            }
            log("--- end of GATT services ---")
            handler.post { statusText.text = "Connected -- ${characteristicListContainer.childCount} writable characteristic(s)" }
        }

        override fun onCharacteristicWrite(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) {
            log("Write to ${characteristic.uuid} -> status=$status (${if (status == 0) "SUCCESS" else "FAILED"})")
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

    @Suppress("DEPRECATION")
    private fun sendHexToSelected() {
        val characteristic = selectedCharacteristic
        val g = gatt
        if (characteristic == null || g == null) {
            log("No characteristic selected -- connect and tap a writable characteristic first.")
            return
        }
        val hex = hexBytesInput.text.toString().trim()
        val bytes = try {
            hex.split(Regex("[\\s,]+")).filter { it.isNotBlank() }
                .map { it.removePrefix("0x").removePrefix("0X").toInt(16).toByte() }
                .toByteArray()
        } catch (e: Exception) {
            log("Could not parse hex bytes '$hex': ${e.message}")
            return
        }
        if (bytes.isEmpty()) {
            log("Enter hex bytes first, e.g. 55 AA 01")
            return
        }
        log("Writing ${bytes.joinToString(" ") { "%02X".format(it) }} to ${characteristic.uuid}")
        characteristic.value = bytes
        try {
            val ok = g.writeCharacteristic(characteristic)
            if (!ok) log("writeCharacteristic() returned false (queue busy or invalid state)")
        } catch (e: SecurityException) {
            log("Missing BLUETOOTH_CONNECT permission to write: ${e.message}")
        }
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
