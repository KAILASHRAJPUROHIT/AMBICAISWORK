package com.mdmesh.agent

import android.app.admin.DevicePolicyManager
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.lifecycle.lifecycleScope
import com.mdmesh.agent.admin.AdminReceiver
import com.mdmesh.core.sync.EnrollmentException
import com.mdmesh.core.sync.EnrollmentManager
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * "Lite" tier linking screen — the on-device counterpart to [EnrollmentManager.enrollWithCredentials].
 * Unlike full enrollment (factory-reset + QR, which lands here via Device-Owner provisioning and
 * never shows any UI of its own), there was previously no on-device enrollment UI at all: this is
 * the first one. Reachable by installing the APK on an already-set-up device with no factory reset.
 *
 * Flow: activate Device Admin (system consent dialog) -> enter email + master password (the same
 * credentials as the admin console) -> [EnrollmentManager.enrollWithCredentials] -> on success,
 * hand off to [PermissionsChecklistActivity], which owns starting the check-in service and
 * finishing into [MainActivity] once its checklist is done.
 */
@AndroidEntryPoint
class LinkDeviceActivity : ComponentActivity() {

    @Inject lateinit var enrollmentManager: EnrollmentManager

    private lateinit var statusText: TextView
    private lateinit var emailField: EditText
    private lateinit var passwordField: EditText
    private lateinit var linkButton: Button

    private val adminComponent by lazy { AdminReceiver.componentName(this) }
    private val dpm by lazy { getSystemService(DEVICE_POLICY_SERVICE) as DevicePolicyManager }

    private val addDeviceAdminLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        if (dpm.isAdminActive(adminComponent)) {
            submitCredentials()
        } else {
            setStatus("Device Admin activation was cancelled — required to link this device.")
            linkButton.isEnabled = true
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(buildUi())
    }

    private fun onLinkClicked() {
        val email = emailField.text.toString().trim()
        val password = passwordField.text.toString()
        if (email.isEmpty() || password.isEmpty()) {
            setStatus("Enter both email and password.")
            return
        }
        linkButton.isEnabled = false
        setStatus("Checking…")

        if (dpm.isAdminActive(adminComponent)) {
            submitCredentials()
            return
        }
        // Activate Device Admin BEFORE touching the network — a device that refuses admin
        // activation should never even attempt credential validation.
        val intent = Intent(DevicePolicyManager.ACTION_ADD_DEVICE_ADMIN).apply {
            putExtra(DevicePolicyManager.EXTRA_DEVICE_ADMIN, adminComponent)
            putExtra(
                DevicePolicyManager.EXTRA_ADD_EXPLANATION,
                "Required to link this device to AMBIC Digital MDM (Lite mode — no factory reset).",
            )
        }
        setStatus("Activate Device Admin to continue…")
        addDeviceAdminLauncher.launch(intent)
    }

    private fun submitCredentials() {
        val email = emailField.text.toString().trim()
        val password = passwordField.text.toString()
        setStatus("Linking…")
        lifecycleScope.launch {
            try {
                enrollmentManager.enrollWithCredentials(email, password)
                setStatus("Linked.")
                finishToPermissions()
            } catch (e: EnrollmentException) {
                setStatus("Failed: ${e.message}")
                linkButton.isEnabled = true
            } catch (e: Exception) {
                setStatus("Failed: ${e.message ?: "unknown error"}")
                linkButton.isEnabled = true
            }
        }
    }

    private fun finishToPermissions() {
        startActivity(
            Intent(this, PermissionsChecklistActivity::class.java)
                .putExtra(PermissionsChecklistActivity.EXTRA_FROM_ENROLLMENT, true),
        )
        finish()
    }

    private fun setStatus(message: String) {
        statusText.text = message
    }

    private fun buildUi(): ScrollView {
        val dp = { v: Int -> (v * resources.displayMetrics.density).toInt() }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#0F1216"))
            setPadding(dp(28), dp(48), dp(28), dp(28))
        }

        fun label(text: String, size: Float, bold: Boolean = false) = TextView(this).apply {
            this.text = text
            textSize = size
            setTextColor(Color.WHITE)
            if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
            setPadding(0, dp(8), 0, dp(8))
        }

        fun input(hint: String, password: Boolean = false) = EditText(this).apply {
            this.hint = hint
            setTextColor(Color.WHITE)
            setHintTextColor(Color.parseColor("#8992A0"))
            if (password) inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }

        root.addView(label("Link this device", 24f, bold = true))
        root.addView(
            label(
                "Lite mode — no factory reset. Enter the same email and master password used " +
                    "for the admin console.",
                14f,
            ),
        )

        emailField = input("Email").also { it.inputType = InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS }
        root.addView(emailField)

        passwordField = input("Master password", password = true)
        root.addView(passwordField)

        linkButton = Button(this).apply {
            text = "Activate & Link"
            setOnClickListener { onLinkClicked() }
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(16)
            }
        }
        root.addView(linkButton)

        statusText = TextView(this).apply {
            setTextColor(Color.parseColor("#8992A0"))
            gravity = Gravity.START
            setPadding(0, dp(16), 0, 0)
        }
        root.addView(statusText)

        return ScrollView(this).apply {
            addView(root)
            layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        }
    }
}
