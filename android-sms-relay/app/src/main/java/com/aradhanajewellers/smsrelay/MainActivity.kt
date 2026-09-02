package com.aradhanajewellers.smsrelay

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.android.material.materialswitch.MaterialSwitch

class MainActivity : AppCompatActivity() {
    private lateinit var enabled: MaterialSwitch
    private lateinit var forwardAll: MaterialSwitch
    private lateinit var smtpHost: EditText
    private lateinit var smtpPort: EditText
    private lateinit var smtpUser: EditText
    private lateinit var smtpPassword: EditText
    private lateinit var recipient: EditText
    private lateinit var whitelist: EditText
    private lateinit var status: TextView
    private lateinit var store: RelayConfigStore

    private val permissionRequest = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { updatePermissionStatus() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = RelayConfigStore(this)
        setContentView(buildContent())
        loadConfig()
        updatePermissionStatus()
    }

    private fun buildContent(): ScrollView {
        val padding = (20 * resources.displayMetrics.density).toInt()
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding, padding, padding)
        }

        column.addView(title("Aradhana SMS Relay"))
        column.addView(note("Rootless bank-SMS relay. Only approved bank sender IDs are forwarded. No SMS leaves this phone unless you enable the relay."))

        enabled = MaterialSwitch(this).apply { text = "Enable bank SMS forwarding" }
        column.addView(enabled)
        forwardAll = MaterialSwitch(this).apply {
            text = "Forward every incoming SMS (includes OTPs and personal messages)"
            setOnCheckedChangeListener { _, checked ->
                whitelist.isEnabled = !checked
                whitelist.alpha = if (checked) 0.45f else 1f
            }
        }
        column.addView(forwardAll)
        smtpHost = field("SMTP host", "smtp.gmail.com")
        smtpPort = field("SMTP port", "465", InputType.TYPE_CLASS_NUMBER)
        smtpUser = field("SMTP username / Gmail address", "relay@example.com", InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS)
        smtpPassword = field("SMTP app password", "Leave blank to keep existing password", InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD)
        recipient = field("Auditor mailbox recipient", "bankalerts@example.com", InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS)
        whitelist = field("Approved bank sender IDs", "One per line. Exact value or prefix ending in *", InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE, 5)

        listOf(smtpHost, smtpPort, smtpUser, smtpPassword, recipient, whitelist).forEach(column::addView)
        column.addView(note("Examples: VM-ICICIB, AD-HDFCBK, AX-*, SBI*. Do not leave this empty. Personal messages and OTPs are not forwarded unless their sender is explicitly allowed."))

        val permissionButton = Button(this).apply {
            text = "Grant SMS permissions"
            setOnClickListener { requestPermissionsIfNeeded() }
        }
        val saveButton = Button(this).apply {
            text = "Save and enable relay"
            setOnClickListener { saveConfig(enableRelay = true) }
        }
        val testButton = Button(this).apply {
            text = "Send safe test email"
            setOnClickListener {
                if (saveConfig(enableRelay = enabled.isChecked)) {
                    val sender = whitelist.text.lines().firstOrNull { it.trim().isNotEmpty() }?.trim()?.removeSuffix("*")
                    if (sender.isNullOrBlank()) {
                        toast("Add an approved sender first.")
                    } else {
                        RelayScheduler.enqueue(this@MainActivity, sender, "Test relay message. No bank payment was processed.", System.currentTimeMillis())
                        toast("Test queued. Check the recipient mailbox shortly.")
                    }
                }
            }
        }
        column.addView(permissionButton)
        column.addView(saveButton)
        column.addView(testButton)
        status = note("")
        status.setPadding(0, padding, 0, 0)
        column.addView(status)

        return ScrollView(this).apply { addView(column) }
    }

    private fun title(value: String) = TextView(this).apply {
        text = value
        textSize = 26f
        setTypeface(typeface, 1)
    }

    private fun note(value: String) = TextView(this).apply {
        text = value
        textSize = 14f
        setPadding(0, 12, 0, 12)
    }

    private fun field(label: String, hint: String, type: Int = InputType.TYPE_CLASS_TEXT, lines: Int = 1): EditText {
        return EditText(this).apply {
            this.hint = "$label — $hint"
            inputType = type
            minLines = lines
            maxLines = lines
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
    }

    private fun loadConfig() {
        val config = store.load()
        enabled.isChecked = config.enabled
        forwardAll.isChecked = config.forwardAllMessages
        smtpHost.setText(config.smtpHost)
        smtpPort.setText(config.smtpPort.toString())
        smtpUser.setText(config.smtpUsername)
        recipient.setText(config.recipient)
        whitelist.setText(config.senderWhitelist.joinToString("\n"))
        whitelist.isEnabled = !config.forwardAllMessages
        whitelist.alpha = if (config.forwardAllMessages) 0.45f else 1f
        // Never render an existing encrypted app password back into the UI.
    }

    private fun saveConfig(enableRelay: Boolean): Boolean {
        val existing = store.load()
        val config = RelayConfig(
            enabled = enableRelay,
            forwardAllMessages = forwardAll.isChecked,
            smtpHost = smtpHost.text.toString(),
            smtpPort = smtpPort.text.toString().toIntOrNull() ?: 0,
            smtpUsername = smtpUser.text.toString(),
            smtpPassword = smtpPassword.text.toString().ifBlank { existing.smtpPassword },
            recipient = recipient.text.toString(),
            senderWhitelist = whitelist.text.lines().map { it.trim() }.filter { it.isNotEmpty() },
        )
        if (!store.isValid(config)) {
            toast("Complete SMTP settings, recipient and app password. Add an approved sender unless Forward every incoming SMS is enabled.")
            return false
        }
        store.save(config)
        enabled.isChecked = enableRelay
        toast(if (enableRelay) "Relay enabled." else "Settings saved. Relay remains disabled.")
        return true
    }

    private fun requestPermissionsIfNeeded() {
        val required = buildList {
            if (ContextCompat.checkSelfPermission(this@MainActivity, Manifest.permission.RECEIVE_SMS) != PackageManager.PERMISSION_GRANTED) add(Manifest.permission.RECEIVE_SMS)
        }
        if (required.isEmpty()) updatePermissionStatus() else permissionRequest.launch(required.toTypedArray())
    }

    private fun updatePermissionStatus() {
        val smsAllowed = ContextCompat.checkSelfPermission(this, Manifest.permission.RECEIVE_SMS) == PackageManager.PERMISSION_GRANTED
        status.text = if (smsAllowed) {
            "SMS permission: granted. Next: set Battery usage to Unrestricted and allow Auto-start in the phone settings."
        } else {
            "SMS permission: missing. Tap ‘Grant SMS permissions’; the relay cannot receive bank alerts until it is granted."
        }
    }

    private fun toast(value: String) = Toast.makeText(this, value, Toast.LENGTH_LONG).show()
}
