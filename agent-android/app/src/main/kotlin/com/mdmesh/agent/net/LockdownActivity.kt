package com.mdmesh.agent.net

import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.lifecycle.lifecycleScope
import com.mdmesh.agent.R
import com.mdmesh.core.store.AdminPasscodeStore
import com.mdmesh.core.store.KioskStateStore
import com.mdmesh.proto.PasscodeHash
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Complete lockdown after 30 minutes without internet. Nothing on the tablet is usable. An administrator enters the MDM
 * exit password, then uses "Trigger tablet unlock": a code is emailed to the owner and must be typed here. Only then does
 * the tablet return to normal.
 */
@AndroidEntryPoint
class LockdownActivity : GuardActivity() {
    @Inject lateinit var guard: ConnectivityGuard
    @Inject lateinit var api: LockdownApi
    @Inject lateinit var kioskStore: KioskStateStore
    @Inject lateinit var passcodeStore: AdminPasscodeStore

    override val backgroundColor: Int = Color.parseColor("#0B0B0F")
    private lateinit var status: TextView
    private var dialog: AlertDialog? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        column.addView(text("\uD83D\uDD12", 72f))
        column.addView(text("Tablet locked", 38f, bold = true, topDp = 16))
        column.addView(text("This tablet had no internet for more than 30 minutes and is locked.\nOnly an administrator can unlock it.", 22f, Color.parseColor("#D0D3DA"), topDp = 16))
        status = text("", 16f, Color.parseColor("#8A8F9C"), topDp = 40)
        column.addView(status)
        column.addView(Button(this).apply {
            text = "Administrator"
            textSize = 18f
            setOnClickListener { askPassword() }
            layoutParams = LinearLayout.LayoutParams(if (isPhone) ViewGroup.LayoutParams.MATCH_PARENT else dp(260), ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(if (isPhone) 28 else 40); gravity = Gravity.CENTER_HORIZONTAL }
        })
    }

    override fun markVisible(v: Boolean) { GuardUi.lockdownVisible = v }

    override fun onDestroy() {
        dialog?.dismiss()
        super.onDestroy()
    }

    override fun onTick() {
        if (!GuardUi.lockdownWanted) { finish(); return }
        val dots = ".".repeat(((System.currentTimeMillis() / 1000) % 4).toInt())
        status.text = (if (GuardUi.online) "Connected \u00B7 waiting for an administrator" else "Trying to reconnect to Wi-Fi$dots") +
            "\nAttempt ${GuardUi.attempts}"
    }

    // ---- administrator flow ------------------------------------------------------------------

    private fun askPassword() {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            hint = "MDM exit password"
        }
        GuardUi.adminUntil = System.currentTimeMillis() + ADMIN_WINDOW_MS
        dialog = AlertDialog.Builder(this)
            .setTitle("Administrator")
            .setMessage("Enter the MDM exit password.")
            .setView(input)
            .setPositiveButton("Continue") { _, _ ->
                val entered = input.text.toString()
                lifecycleScope.launch {
                    if (passwordOk(entered)) adminPanel() else toast("That password isn't right.")
                }
            }
            .setNegativeButton("Cancel") { _, _ -> GuardUi.adminUntil = 0L }
            .show()
    }

    /** The same two passwords that open the kiosk admin menu: the one set with the kiosk, or the fleet-wide passcode. */
    private suspend fun passwordOk(entered: String): Boolean {
        if (entered.isBlank()) return false
        val kiosk = runCatching { kioskStore.load() ?: kioskStore.loadLastKnown() }.getOrNull()?.password
        val fleet = runCatching { passcodeStore.load() }.getOrNull()
        return (kiosk != null && kiosk == entered) || (!fleet.isNullOrBlank() && PasscodeHash.matches(entered, fleet))
    }

    private fun adminPanel() {
        GuardUi.adminUntil = System.currentTimeMillis() + ADMIN_WINDOW_MS
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(24), dp(8), dp(24), 0) }
        box.addView(Button(this).apply { text = "Connect to Wi-Fi"; setOnClickListener { openWifi() } })
        box.addView(Button(this).apply { text = "Trigger tablet unlock"; setOnClickListener { dialog?.dismiss(); triggerUnlock() } })
        dialog = AlertDialog.Builder(this)
            .setTitle("MDM administrator")
            .setMessage("Connect the tablet to a network if it is offline, then trigger the unlock. A code is emailed to the owner.")
            .setView(box)
            .setNegativeButton("Close") { _, _ -> GuardUi.adminUntil = 0L }
            .show()
    }

    private fun openWifi() {
        GuardUi.adminUntil = System.currentTimeMillis() + ADMIN_WINDOW_MS
        runCatching { stopLockTask() }
        val panel = Intent(Settings.Panel.ACTION_INTERNET_CONNECTIVITY)
        runCatching { startActivity(panel) }.onFailure {
            runCatching { startActivity(Intent(Settings.ACTION_WIFI_SETTINGS)) }
        }
    }

    private fun triggerUnlock() {
        GuardUi.adminUntil = System.currentTimeMillis() + ADMIN_WINDOW_MS
        toast("Sending the code\u2026")
        lifecycleScope.launch {
            val r = api.requestCode()
            if (!r.ok) { toast(r.message); adminPanel(); return@launch }
            askCode(r.sentTo)
        }
    }

    private fun askCode(sentTo: String) {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
            hint = "6-digit code"
        }
        dialog = AlertDialog.Builder(this)
            .setTitle("Enter the unlock code")
            .setMessage("A code was emailed to ${sentTo.ifBlank { "the owner" }}. It is valid for 10 minutes.")
            .setView(input)
            .setCancelable(false)
            .setPositiveButton("Unlock") { _, _ ->
                lifecycleScope.launch {
                    val r = api.verify(input.text.toString().trim())
                    if (r.ok) {
                        guard.release("emailed code")
                        GuardUi.adminUntil = 0L
                        toast("Tablet unlocked.")
                        finish()
                    } else {
                        toast(r.message)
                        askCode(sentTo)
                    }
                }
            }
            .setNegativeButton("Cancel") { _, _ -> GuardUi.adminUntil = 0L }
            .show()
    }

    private fun toast(msg: String) = android.widget.Toast.makeText(this, msg, android.widget.Toast.LENGTH_LONG).show()

    private companion object {
        const val ADMIN_WINDOW_MS = 10 * 60_000L
    }
}
