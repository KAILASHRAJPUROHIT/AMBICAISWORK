package com.mdmesh.agent

import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import com.mdmesh.agent.service.CheckInService
import com.mdmesh.core.permission.PermissionCheck
import com.mdmesh.core.permission.PermissionRegistry
import dagger.hilt.android.AndroidEntryPoint

/**
 * On-device permissions checklist — one row per [PermissionCheck] in [PermissionRegistry].
 * Reached either right after a fresh Lite-tier link ([LinkDeviceActivity], with
 * [EXTRA_FROM_ENROLLMENT] set, where "Done" proceeds into [MainActivity]) or manually from
 * [MainActivity]'s "Review permissions" button on an already-enrolled device (no extra, "Done"
 * just closes back to it).
 *
 * None of these rows are Device-Owner-silent-grantable — they're AppOps/special-access
 * permissions, not manifest runtime permissions, so `DevicePolicyManager.setPermissionGrantState`
 * doesn't reach any of them. This screen is shown and walked through the same way on every
 * device tier, Device-Owner or Lite.
 */
@AndroidEntryPoint
class PermissionsChecklistActivity : ComponentActivity() {

    private val rows = PermissionRegistry.checklist()
    private val statusViews = mutableMapOf<String, TextView>()
    private val skipped = mutableSetOf<String>()

    private val settingsLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { refreshAll() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(buildUi())
    }

    override fun onResume() {
        super.onResume()
        refreshAll()
    }

    private fun refreshAll() {
        rows.forEach { row -> statusViews[row.key]?.let { applyStatus(it, row) } }
    }

    private fun applyStatus(view: TextView, row: PermissionCheck) {
        val granted = row.isGranted(this)
        view.text = when {
            granted -> "Granted"
            skipped.contains(row.key) -> "Skipped"
            !row.verifiable -> "Can't verify — tap to open"
            else -> "Not granted"
        }
        view.setTextColor(if (granted) OK else if (skipped.contains(row.key)) MUTED else ALERT)
    }

    private fun onDone() {
        if (intent.getBooleanExtra(EXTRA_FROM_ENROLLMENT, false)) {
            ContextCompat.startForegroundService(this, Intent(this, CheckInService::class.java))
            startActivity(Intent(this, MainActivity::class.java))
        }
        finish()
    }

    private fun buildUi(): ScrollView {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(INK)
            setPadding(dp(28), dp(40), dp(28), dp(28))
            layoutParams = ViewGroup.LayoutParams(MATCH, MATCH)
        }

        root.addView(text("Permissions", 24f, TEXT, bold = true))
        root.addView(
            text(
                "Grant these so the console can fully manage this device. Some can be skipped for now.",
                14f,
                MUTED,
            ).apply { setPadding(0, dp(4), 0, dp(20)) },
        )

        rows.forEach { row -> root.addView(buildRow(row)) }

        val done = Button(this).apply {
            text = "Done"
            setOnClickListener { onDone() }
            layoutParams = LinearLayout.LayoutParams(MATCH, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(20)
            }
        }
        root.addView(done)

        return ScrollView(this).apply {
            setBackgroundColor(INK)
            addView(root)
            layoutParams = ViewGroup.LayoutParams(MATCH, MATCH)
        }
    }

    private fun buildRow(row: PermissionCheck): View {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(14), 0, dp(14))
            isClickable = true
            isFocusable = true
            setOnClickListener {
                skipped.remove(row.key)
                runCatching { settingsLauncher.launch(row.settingsIntent(this@PermissionsChecklistActivity)) }
            }
        }

        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(MATCH, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
        header.addView(
            text(row.label, 16f, TEXT).apply {
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            },
        )
        val status = text("…", 13f, MUTED).apply { gravity = Gravity.END }
        statusViews[row.key] = status
        header.addView(status)
        container.addView(header)

        container.addView(text(row.description, 13f, MUTED).apply { setPadding(0, dp(4), 0, 0) })

        if (row.skippable) {
            container.addView(
                text("Skip", 13f, FAINT).apply {
                    setPadding(0, dp(6), 0, 0)
                    setOnClickListener {
                        skipped.add(row.key)
                        refreshAll()
                    }
                },
            )
        }

        applyStatus(status, row)
        return container
    }

    private fun text(s: String, sizeSp: Float, color: Int, bold: Boolean = false): TextView =
        TextView(this).apply {
            text = s
            setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp)
            setTextColor(color)
            if (bold) setTypeface(typeface, Typeface.BOLD)
        }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    companion object {
        const val EXTRA_FROM_ENROLLMENT = "from_enrollment"

        private const val MATCH = ViewGroup.LayoutParams.MATCH_PARENT
        private val INK = Color.parseColor("#0E1117")
        private val TEXT = Color.parseColor("#E8EEF4")
        private val MUTED = Color.parseColor("#8693A4")
        private val FAINT = Color.parseColor("#5C6675")
        private val OK = Color.parseColor("#3FD08A")
        private val ALERT = Color.parseColor("#F2545B")
    }
}
