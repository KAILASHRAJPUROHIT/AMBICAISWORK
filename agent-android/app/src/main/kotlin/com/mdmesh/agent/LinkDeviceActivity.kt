package com.mdmesh.agent

import android.app.admin.DevicePolicyManager
import android.content.Intent
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
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
    private lateinit var progress: ProgressBar

    private val adminComponent by lazy { AdminReceiver.componentName(this) }
    private val dpm by lazy { getSystemService(DEVICE_POLICY_SERVICE) as DevicePolicyManager }

    private val addDeviceAdminLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        if (dpm.isAdminActive(adminComponent)) {
            submitCredentials()
        } else {
            setStatus("Device Admin activation was cancelled — required to link this device.", isError = true)
            setBusy(false)
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
            setStatus("Enter both email and password.", isError = true)
            return
        }
        setBusy(true)
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
                setStatus("Failed: ${e.message}", isError = true)
                setBusy(false)
            } catch (e: Exception) {
                setStatus("Failed: ${e.message ?: "unknown error"}", isError = true)
                setBusy(false)
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

    private fun setStatus(message: String, isError: Boolean = false) {
        statusText.text = message
        statusText.setTextColor(
            ContextCompat.getColor(this, if (isError) R.color.brand_error else R.color.brand_text_muted),
        )
    }

    private fun setBusy(busy: Boolean) {
        linkButton.isEnabled = !busy
        linkButton.alpha = if (busy) 0.6f else 1f
        progress.visibility = if (busy) android.view.View.VISIBLE else android.view.View.GONE
    }

    private fun buildUi(): ScrollView {
        val dp = { v: Int -> (v * resources.displayMetrics.density).toInt() }
        val ink = ContextCompat.getColor(this, R.color.brand_ink)
        val surface = ContextCompat.getColor(this, R.color.brand_surface)
        val text = ContextCompat.getColor(this, R.color.brand_text)
        val muted = ContextCompat.getColor(this, R.color.brand_text_muted)
        val accent = ContextCompat.getColor(this, R.color.brand_accent)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setBackgroundColor(ink)
            setPadding(dp(28), dp(56), dp(28), dp(28))
        }

        fun fieldBackground() = GradientDrawable().apply {
            cornerRadius = dp(12).toFloat()
            setColor(surface)
            setStroke(dp(1), ContextCompat.getColor(this@LinkDeviceActivity, R.color.brand_text_muted))
        }

        // Logo — the app's own launcher mark, so this first screen a person ever sees carries the
        // same identity as the icon on their home screen instead of a bare wall of text.
        root.addView(
            ImageView(this).apply {
                setImageResource(R.mipmap.ic_launcher)
                layoutParams = LinearLayout.LayoutParams(dp(72), dp(72))
            },
        )

        root.addView(
            TextView(this).apply {
                this.text = "AMBIC MDM"
                textSize = 22f
                setTextColor(text)
                setTypeface(typeface, android.graphics.Typeface.BOLD)
                setPadding(0, dp(16), 0, dp(4))
            },
        )
        root.addView(
            TextView(this).apply {
                this.text = "Link this device"
                textSize = 15f
                setTextColor(muted)
                gravity = Gravity.CENTER_HORIZONTAL
            },
        )
        root.addView(
            TextView(this).apply {
                this.text = "Lite mode — no factory reset. Enter the same email and master " +
                    "password used for the admin console."
                textSize = 13f
                setTextColor(muted)
                gravity = Gravity.CENTER_HORIZONTAL
                setPadding(0, dp(12), 0, dp(24))
            },
        )

        // Card — groups the two inputs and the primary action visually, instead of them floating
        // loose against the plain background.
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = GradientDrawable().apply {
                cornerRadius = dp(20).toFloat()
                setColor(surface)
            }
            setPadding(dp(20), dp(24), dp(20), dp(24))
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }

        fun input(hint: String, password: Boolean = false) = EditText(this).apply {
            this.hint = hint
            setTextColor(text)
            setHintTextColor(muted)
            background = fieldBackground()
            setPadding(dp(14), dp(14), dp(14), dp(14))
            if (password) inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(12)
            }
        }

        emailField = input("Email").also { it.inputType = InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS }
        card.addView(emailField)

        passwordField = input("Master password", password = true).also { it.layoutParams = (it.layoutParams as LinearLayout.LayoutParams).apply { bottomMargin = 0 } }
        card.addView(passwordField)

        val actionRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(20), 0, 0)
        }

        linkButton = Button(this).apply {
            this.text = "Activate & Link"
            setTextColor(ink)
            background = GradientDrawable().apply {
                cornerRadius = dp(12).toFloat()
                setColor(accent)
            }
            setOnClickListener { onLinkClicked() }
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                marginEnd = dp(12)
            }
        }
        actionRow.addView(linkButton)

        progress = ProgressBar(this).apply {
            visibility = android.view.View.GONE
            indeterminateTintList = android.content.res.ColorStateList.valueOf(accent)
        }
        actionRow.addView(progress)
        card.addView(actionRow)
        root.addView(card)

        statusText = TextView(this).apply {
            setTextColor(muted)
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(0, dp(20), 0, 0)
        }
        root.addView(statusText)

        // Android 15 (targetSdk 35) draws edge-to-edge by default — pad the scroll content by the
        // system bar insets so the logo isn't tucked under the status bar and the status text at
        // the bottom isn't cut by the nav bar (same class of bug fixed in KioskLauncherActivity).
        val scroll = ScrollView(this).apply {
            addView(root)
            layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        }
        ViewCompat.setOnApplyWindowInsetsListener(scroll) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            root.setPadding(dp(28), dp(28) + bars.top, dp(28), dp(28) + bars.bottom)
            insets
        }
        return scroll
    }
}
