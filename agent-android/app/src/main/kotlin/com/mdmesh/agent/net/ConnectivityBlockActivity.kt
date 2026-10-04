package com.mdmesh.agent.net

import android.graphics.Color
import android.os.Bundle
import android.widget.TextView
import dagger.hilt.android.AndroidEntryPoint

/** Shown after 10 minutes without internet: the tablet is unusable until it reconnects. Closes itself when it does. */
@AndroidEntryPoint
class ConnectivityBlockActivity : GuardActivity() {
    override val backgroundColor: Int = Color.parseColor("#7A0F14")
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        column.addView(text("\u26A0", 72f, topDp = 0))
        column.addView(text("This device cannot be used without internet", 34f, bold = true, topDp = 16))
        column.addView(text("Contact your administrator.", 24f, topDp = 16))
        status = text("", 18f, Color.parseColor("#FFD9DB"), topDp = 48)
        column.addView(status)
    }

    override fun markVisible(v: Boolean) { GuardUi.blockVisible = v }

    override fun onTick() {
        // The guard clears this when the internet is back, or when the screen escalates to lockdown.
        if (!GuardUi.blockWanted) { finish(); return }
        val dots = ".".repeat(((System.currentTimeMillis() / 1000) % 4).toInt())
        status.text = "Trying to reconnect to Wi-Fi$dots\nAttempt ${GuardUi.attempts} \u00B7 offline for ${minutesOffline()} min" +
            (if (GuardUi.openSeen > 0) "\nLooking for open networks: ${GuardUi.openSeen} in range" else "\nLooking for open networks\u2026")
    }
}
