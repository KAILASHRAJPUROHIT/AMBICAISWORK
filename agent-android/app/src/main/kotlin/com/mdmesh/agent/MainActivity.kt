package com.mdmesh.agent

import android.Manifest
import android.app.ActivityManager
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.content.Intent
import androidx.activity.ComponentActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.mdmesh.agent.admin.DeviceOwnerInitializer
import com.mdmesh.agent.service.CheckInService
import com.mdmesh.core.config.ServerConfigStore
import com.mdmesh.core.store.DeviceIdStore
import com.mdmesh.core.store.KioskStateStore
import com.mdmesh.core.sync.SyncStatus
import com.mdmesh.kiosk.KioskController
import com.mdmesh.kiosk.KioskResult
import com.mdmesh.kiosk.KioskToggles
import com.mdmesh.kiosk.lockTaskFeatures
import com.mdmesh.policy.wifi.DpmHandle
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import java.text.DateFormat
import java.util.Date
import javax.inject.Inject
import android.view.View
import android.widget.FrameLayout
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.mdmesh.core.state.KioskStatusSource
import com.mdmesh.core.store.ClientBrandingStore
import com.mdmesh.core.store.KioskSectionsStore
import com.mdmesh.agent.ui.loadBrandBitmap
import android.widget.ImageView
import com.mdmesh.agent.ui.GroundDrawable
import com.mdmesh.agent.ui.Metrics
import com.mdmesh.agent.ui.Palette
import com.mdmesh.agent.ui.ScoreRingView
import com.mdmesh.agent.ui.breathe
import com.mdmesh.agent.ui.enter
import com.mdmesh.agent.ui.gradient
import com.mdmesh.agent.ui.pressable
import com.mdmesh.agent.ui.rounded
import com.mdmesh.agent.ui.style
import com.mdmesh.agent.ui.withAlpha

/**
 * MDMesh agent home / status screen. Doubles as the kiosk HOME surface
 * (`android:lockTaskMode="if_whitelisted"` + HOME intent filter), so when the agent's
 * package is lock-task-allowlisted the system auto-enters lock task here.
 *
 * Shows the real managed state — Device-Owner status, server-issued device id, kiosk state,
 * and the server URL — so a person looking at the device can see it's managed by MDMesh.
 */
@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject lateinit var deviceIdStore: DeviceIdStore
    @Inject lateinit var dpmHandle: DpmHandle
    @Inject lateinit var serverConfig: ServerConfigStore
    @Inject lateinit var syncStatus: SyncStatus
    @Inject lateinit var kioskController: KioskController
    @Inject lateinit var kioskStateStore: KioskStateStore

    private lateinit var deviceIdValue: TextView
    private lateinit var kioskValue: TextView
    private lateinit var reenterKioskButton: Button

    /** Same alias KioskEnterHandler pins as HOME while in kiosk — see AgentModule.kioskHomeAlias. */
    private val kioskHomeAlias: ComponentName
        get() = ComponentName(packageName, "com.mdmesh.agent.KioskHomeAlias")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Sideloaded (no factory-reset/QR provisioning ran), not Device Owner, and never
        // enrolled: this is a fresh "Lite" tier install. Send it straight to the linking screen
        // rather than showing a status screen for a device with nothing to show yet.
        if (!isDeviceOwner()) {
            lifecycleScope.launch {
                if (deviceIdStore.current().isNullOrBlank()) {
                    startActivity(Intent(this@MainActivity, LinkDeviceActivity::class.java))
                    finish()
                }
            }
        }
        setContentView(buildUi())
        // Provisioning callbacks must return without policy work; Android 16 otherwise can abort
        // Device Owner setup. Apply the same baseline only after Setup Wizard has launched us.
        lifecycleScope.launch(Dispatchers.Default) {
            DeviceOwnerInitializer.apply(applicationContext)
        }
        // Grant our own POST_NOTIFICATIONS as Device Owner BEFORE starting the foreground
        // service, so the "MDMesh active" notification is visible on Android 13+.
        grantSelfNotifications()
        // NOTE: we intentionally do NOT pop the battery-optimization request dialog here. As a
        // foreground-service Device Owner we survive Doze well enough, and that full-screen system
        // dialog used to sit on top and pause the kiosk launcher, so a kiosk.enter wouldn't take
        // visible effect until the user dismissed it. There is no public Device-Owner API to grant
        // the Doze exemption silently, so the safest behaviour is to not interrupt.
        // Start the near-real-time command channel (foreground poll loop). Starting from the
        // launcher activity keeps us in the foreground-start allowance on Android 12+.
        ContextCompat.startForegroundService(this, Intent(this, CheckInService::class.java))
        refresh()
    }

    /** Self-grant POST_NOTIFICATIONS (Device Owner, API 33+) so our FGS notification shows. */
    private fun grantSelfNotifications() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        runCatching {
            val dpm = dpmHandle.dpm
            if (dpm.isDeviceOwnerApp(packageName)) {
                dpm.setPermissionGrantState(
                    dpmHandle.admin,
                    packageName,
                    Manifest.permission.POST_NOTIFICATIONS,
                    DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED,
                )
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // refresh() now, then every 5s while visible so the health rows stay live.
        tickHandler.removeCallbacks(tick)
        tickHandler.post(tick)
    }

    private fun refresh() {
        val locked = isLocked()
        kioskValue.text = if (locked) "Locked (kiosk active)" else "Not locked"
        renderChecks()
        lastCheckIn.text = syncStatus.lastOkAt.value?.let { relative(it) } ?: "—"
        val host = serverConfig.baseUrl().removePrefix("https://").removePrefix("http://")
        serverLine.text = when {
            syncStatus.lastError.value != null -> "Can't reach $host: ${syncStatus.lastError.value?.message}"
            syncStatus.lastOkAt.value != null -> "Connected to $host"
            else -> "Waiting for first check-in · $host"
        }
        serverDot.background = rounded(
            when {
                syncStatus.lastError.value != null -> pal.alert
                syncStatus.lastOkAt.value != null -> pal.ok
                else -> pal.warn
            },
            m.dp(4f),
        )
        lifecycleScope.launch {
            kioskStateStore.loadLastKnown()?.deviceLabel?.takeIf { it.isNotBlank() }?.let { titleView.text = "$it health" }
        }
        lifecycleScope.launch {
            val id = deviceIdStore.current()
            deviceIdValue.text = if (id.isNullOrBlank()) enrollingLabel() else id
        }
        lifecycleScope.launch {
            val hasLastKnown = kioskStateStore.loadLastKnown() != null
            reenterKioskButton.visibility =
                if (!locked && hasLastKnown) android.view.View.VISIBLE else android.view.View.GONE
        }
    }

    /**
     * Re-locks the device to its last-applied kiosk configuration, entirely on-device — no server
     * round-trip needed. Mirrors [com.mdmesh.core.command.handlers.KioskEnterHandler] minus the
     * command-envelope plumbing, since this is a local action, not a remote command.
     */
    private fun reenterKiosk() {
        lifecycleScope.launch {
            val p = kioskStateStore.loadLastKnown()
            if (p == null) {
                // A re-enrolled or freshly reset device has no saved kiosk setup to restore. Say so instead of doing nothing.
                android.widget.Toast.makeText(
                    this@MainActivity,
                    "No kiosk has been set up on this device yet. In the console open this device and choose Enter kiosk.",
                    android.widget.Toast.LENGTH_LONG,
                ).show()
                return@launch
            }
            val features = lockTaskFeatures(
                KioskToggles(
                    home = p.features.home,
                    recents = p.features.recents,
                    notifications = p.features.notifications,
                    systemInfo = p.features.systemInfo,
                    keyguard = p.features.keyguard,
                    lockButtons = p.features.lockButtons,
                ),
            )
            val allowed = (p.allowedPackages + listOfNotNull(p.pinPackage)).distinct()
            setHomeAlias(enabled = true)
            when (kioskController.enter(kioskHomeAlias, allowed, features)) {
                is KioskResult.Ok -> {
                    kioskStateStore.save(p)
                    // Real HOME intent, not a direct component launch — see KioskEnterHandler's
                    // foregroundLauncher() for why this matters (OEM System UI state refresh).
                    runCatching {
                        startActivity(
                            Intent(Intent.ACTION_MAIN)
                                .addCategory(Intent.CATEGORY_HOME)
                                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                        )
                    }
                }
                else -> setHomeAlias(enabled = false)
            }
            refresh()
        }
    }

    private fun setHomeAlias(enabled: Boolean) {
        runCatching {
            val state = if (enabled) {
                PackageManager.COMPONENT_ENABLED_STATE_ENABLED
            } else {
                PackageManager.COMPONENT_ENABLED_STATE_DISABLED
            }
            packageManager.setComponentEnabledSetting(kioskHomeAlias, state, PackageManager.DONT_KILL_APP)
        }
    }

    /** "Enrolling…" plus the last sync error (if any), so a stuck enrollment is diagnosable on-device. */
    private fun enrollingLabel(): String {
        val failure = syncStatus.lastError.value ?: return "Enrolling…"
        val at = DateFormat.getTimeInstance(DateFormat.SHORT).format(Date(failure.atMillis))
        return "Enrolling… (last error: ${failure.message} at $at)"
    }

    private fun isLocked(): Boolean {
        val am = getSystemService(ACTIVITY_SERVICE) as ActivityManager
        return am.lockTaskModeState == ActivityManager.LOCK_TASK_MODE_LOCKED
    }

    private fun isDeviceOwner(): Boolean =
        dpmHandle.dpm.isDeviceOwnerApp(packageName)

    private class Check(val title: String, val detail: String, val ok: Boolean, val onLabel: String, val offLabel: String, val hint: String)

    private lateinit var pal: Palette
    private lateinit var m: Metrics
    private lateinit var titleView: TextView
    private lateinit var score: ScoreRingView
    private lateinit var summaryTitle: TextView
    private lateinit var summaryText: TextView
    private lateinit var checksBox: LinearLayout
    private lateinit var lastCheckIn: TextView
    private lateinit var serverLine: TextView
    private lateinit var serverDot: View
    private val tickHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() { refresh(); tickHandler.postDelayed(this, 5_000) }
    }

    override fun onPause() {
        tickHandler.removeCallbacks(tick)
        super.onPause()
    }

    /** Agent health screen (Obsidian Pro): score ring, one live row per guard, agent/server facts,
     *  and Re-enter kiosk as the primary action. Sized through [Metrics] for phones and tablets. */
    private fun buildUi(): View {
        pal = Palette.of(this)
        m = Metrics(this)
        val root = FrameLayout(this).apply {
            background = GroundDrawable(pal, m.dp(28f))
            layoutParams = ViewGroup.LayoutParams(MATCH, MATCH)
        }
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        ViewCompat.setOnApplyWindowInsetsListener(col) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            v.setPadding(m.dp(m.gutterDp), bars.top + m.dp(18), m.dp(m.gutterDp), bars.bottom + m.dp(24))
            insets
        }

        // Header: gradient mark + eyebrow + "<device> health".
        val head = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        head.addView(
            TextView(this).apply {
                text = "MDM"
                gravity = Gravity.CENTER
                style(m.sp(11f), Color.WHITE, 800, mono = true)
                background = gradient(intArrayOf(pal.c1, pal.c2, pal.c3), m.dp(13f))
                layoutParams = LinearLayout.LayoutParams(m.dp(44), m.dp(44)).apply { rightMargin = m.dp(12) }
            },
        )
        val headTx = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        headTx.addView(TextView(this).apply { text = "AMBIC DIGITAL · DEVICE AGENT"; style(m.sp(9.5f), pal.c2, 700, mono = true, letterSp = 0.18f) })
        titleView = TextView(this).apply { text = "Device health"; style(m.sp(20f), pal.text, 700); setPadding(0, m.dp(3), 0, 0) }
        headTx.addView(titleView)
        head.addView(headTx.apply {
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        })
        // Client brand on the right: AMBIC DIGITAL owns the agent, the client owns the device.
        val brand = ClientBrandingStore.read(this).let { b ->
            if (KioskSectionsStore.read(this).clientLogo) b else b.copy(logo = null, mark = null)
        }
        val markPx = m.dp(if (m.isPhone) 52 else 64)
        loadBrandBitmap(brand.logo ?: brand.mark, markPx * 3)?.let { bmp ->
            head.addView(
                ImageView(this).apply {
                    setImageBitmap(bmp)
                    adjustViewBounds = true
                    maxHeight = markPx
                    maxWidth = markPx * 2
                    contentDescription = brand.name ?: "Client logo"
                },
            )
        }
        col.addView(head)

        // Score card.
        val scoreCard = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(m.dp(16), m.dp(16), m.dp(16), m.dp(16))
            background = rounded(withAlpha(pal.surface, 0.9f), m.dp(20f), pal.line, m.dp(1))
            layoutParams = LinearLayout.LayoutParams(MATCH, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = m.dp(18) }
            enter(0)
        }
        score = ScoreRingView(this, pal).apply {
            layoutParams = LinearLayout.LayoutParams(m.dp(84), m.dp(84)).apply { rightMargin = m.dp(16) }
        }
        scoreCard.addView(score)
        val sumCol = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        }
        summaryTitle = TextView(this).apply { style(m.sp(15f), pal.text, 700) }
        summaryText = TextView(this).apply { style(m.sp(12.5f), pal.muted); setPadding(0, m.dp(4), 0, 0) }
        sumCol.addView(summaryTitle); sumCol.addView(summaryText)
        scoreCard.addView(sumCol)
        col.addView(scoreCard)

        checksBox = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded(withAlpha(pal.surface, 0.9f), m.dp(18f), pal.line, m.dp(1))
            clipToOutline = true
            layoutParams = LinearLayout.LayoutParams(MATCH, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = m.dp(12) }
            enter(80)
        }
        col.addView(checksBox)

        // Facts: agent version, last check-in, device id.
        val facts = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(MATCH, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = m.dp(12) }
            enter(140)
        }
        fun fact(label: String, value: TextView, last: Boolean) = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(m.dp(14), m.dp(12), m.dp(14), m.dp(12))
            background = rounded(withAlpha(pal.surface, 0.9f), m.dp(16f), pal.line, m.dp(1))
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { if (!last) rightMargin = m.dp(10) }
            addView(TextView(this@MainActivity).apply { text = label; style(m.sp(9.5f), pal.muted, 700, mono = true, letterSp = 0.16f) })
            addView(value.apply { setPadding(0, m.dp(5), 0, 0) })
        }
        facts.addView(fact("AGENT", TextView(this).apply {
            text = "${com.mdmesh.agent.BuildConfig.VERSION_NAME} · ${com.mdmesh.agent.BuildConfig.VERSION_CODE}"
            style(m.sp(14f), pal.text, 700, mono = true)
        }, false))
        lastCheckIn = TextView(this).apply { style(m.sp(14f), pal.text, 700, mono = true) }
        facts.addView(fact("LAST CHECK-IN", lastCheckIn, true))
        col.addView(facts)

        deviceIdValue = TextView(this).apply { style(m.sp(12.5f), pal.text, 500, mono = true) }
        col.addView(
            LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(m.dp(14), m.dp(12), m.dp(14), m.dp(12))
                background = rounded(withAlpha(pal.surface, 0.9f), m.dp(16f), pal.line, m.dp(1))
                layoutParams = LinearLayout.LayoutParams(MATCH, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = m.dp(10) }
                addView(TextView(this@MainActivity).apply { text = "DEVICE ID"; style(m.sp(9.5f), pal.muted, 700, mono = true, letterSp = 0.16f) })
                addView(deviceIdValue.apply { setPadding(0, m.dp(5), 0, 0) })
                enter(180)
            },
        )

        // Server line with a breathing connection light.
        val server = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(m.dp(4), m.dp(14), 0, 0)
        }
        serverDot = View(this).apply {
            background = rounded(pal.ok, m.dp(4f))
            layoutParams = LinearLayout.LayoutParams(m.dp(7), m.dp(7)).apply { rightMargin = m.dp(8) }
            breathe(2000)
        }
        server.addView(serverDot)
        serverLine = TextView(this).apply { style(m.sp(12f), pal.muted) }
        server.addView(serverLine)
        col.addView(server)

        // Actions.
        val actions = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(MATCH, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = m.dp(18) }
        }
        reenterKioskButton = Button(this).apply {
            text = "Re-enter kiosk"
            isAllCaps = false
            style(m.sp(14f), Color.WHITE, 700)
            background = gradient(intArrayOf(pal.c1, pal.c2), m.dp(14f))
            stateListAnimator = null
            visibility = View.GONE
            layoutParams = LinearLayout.LayoutParams(0, m.dp(50), 1f).apply { rightMargin = m.dp(10) }
            setOnClickListener { reenterKiosk() }
            pressable()
        }
        actions.addView(reenterKioskButton)
        actions.addView(
            Button(this).apply {
                text = "Review permissions"
                isAllCaps = false
                style(m.sp(14f), pal.text, 600)
                background = rounded(pal.surface2, m.dp(14f), pal.line, m.dp(1))
                stateListAnimator = null
                layoutParams = LinearLayout.LayoutParams(0, m.dp(50), 1f)
                setOnClickListener {
                    startActivity(Intent(this@MainActivity, PermissionsChecklistActivity::class.java))
                }
                pressable()
            },
        )
        col.addView(actions)
        col.addView(
            TextView(this).apply {
                text = ClientBrandingStore.read(this@MainActivity).name
                    ?.let { "Managed by AMBIC DIGITAL for $it" } ?: "Managed by AMBIC DIGITAL"
                gravity = Gravity.CENTER
                style(m.sp(11.5f), pal.faint)
                setPadding(0, m.dp(22), 0, 0)
            },
        )
        kioskValue = TextView(this) // kept for refresh(); the Kiosk row shows the state

        val holder = FrameLayout(this)
        val w = if (m.isPhone) MATCH else kotlin.math.min(resources.displayMetrics.widthPixels, m.dp(720))
        holder.addView(col, FrameLayout.LayoutParams(w, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER_HORIZONTAL))
        root.addView(ScrollView(this).apply { isFillViewport = true; addView(holder) })
        return root
    }

    /** The live guard list, most important first. */
    private fun checks(): List<Check> {
        val status = KioskStatusSource.read(this)
        val writeOk = runCatching { android.provider.Settings.System.canWrite(this) }.getOrDefault(false)
        val usageOk = runCatching {
            val ops = getSystemService(APP_OPS_SERVICE) as android.app.AppOpsManager
            val mode = if (Build.VERSION.SDK_INT >= 29) {
                ops.unsafeCheckOpNoThrow(android.app.AppOpsManager.OPSTR_GET_USAGE_STATS, android.os.Process.myUid(), packageName)
            } else {
                @Suppress("DEPRECATION")
                ops.checkOpNoThrow(android.app.AppOpsManager.OPSTR_GET_USAGE_STATS, android.os.Process.myUid(), packageName)
            }
            mode == android.app.AppOpsManager.MODE_ALLOWED
        }.getOrDefault(false)
        val adbOk = runCatching {
            android.provider.Settings.Global.getInt(contentResolver, "adb_wifi_enabled", 0) == 1
        }.getOrDefault(false)
        return listOf(
            Check("Device Owner", if (isDeviceOwner()) "Full management active" else "Not managed", isDeviceOwner(),
                "ACTIVE", "OFF", "This device is not under full management."),
            Check("Kiosk", if (isLocked()) "Home screen locked" else "Not locked", isLocked(),
                "LOCKED", "OFF", "Tap Re-enter kiosk to lock the home screen again."),
            Check("Write access", "Auto-rotate from Quick Controls", writeOk,
                "ON", "OFF", "The shop PC re-grants write access automatically after updates."),
            Check("Usage access", "App time report", usageOk,
                "ON", "OFF", "The shop PC re-grants usage access automatically after updates."),
            Check("Wireless ADB", if (adbOk) "Shop PC can reconnect" else "Shop PC cannot reach it", adbOk,
                "ON", "OFF", "It turns itself back on when the tablet is on shop Wi-Fi."),
            Check("Wi-Fi", if (status.wifiConnected) (status.ssid ?: "Connected") else "Not connected", status.wifiConnected,
                "ON", "OFF", "Wi-Fi comes back on by itself within 3 minutes."),
        )
    }

    private fun renderChecks() {
        val list = checks()
        checksBox.removeAllViews()
        list.forEachIndexed { i, c ->
            if (i > 0) checksBox.addView(View(this).apply {
                setBackgroundColor(pal.line)
                layoutParams = LinearLayout.LayoutParams(MATCH, m.dp(1))
            })
            val tone = if (c.ok) pal.ok else pal.warn
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(m.dp(14), m.dp(11), m.dp(14), m.dp(11))
            }
            row.addView(View(this).apply {
                background = rounded(tone, m.dp(5f))
                elevation = m.dp(2f)
                layoutParams = LinearLayout.LayoutParams(m.dp(9), m.dp(9)).apply { rightMargin = m.dp(12) }
                if (!c.ok) breathe(1400)
            })
            val tx = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            }
            tx.addView(TextView(this).apply { text = c.title; style(m.sp(14f), pal.text, 600) })
            tx.addView(TextView(this).apply { text = c.detail; style(m.sp(11.5f), pal.muted); setPadding(0, m.dp(2), 0, 0) })
            row.addView(tx)
            row.addView(TextView(this).apply {
                text = if (c.ok) c.onLabel else c.offLabel
                style(m.sp(9.5f), tone, 700, mono = true, letterSp = 0.08f)
                setPadding(m.dp(8), m.dp(3), m.dp(8), m.dp(3))
                background = rounded(withAlpha(tone, 0.14f), m.dp(6f))
            })
            checksBox.addView(row)
        }
        val okCount = list.count { it.ok }
        score.set(okCount, list.size)
        val bad = list.filterNot { it.ok }
        summaryTitle.text = when (bad.size) {
            0 -> "Everything is on"
            1 -> "Almost everything is on"
            else -> "${bad.size} things need attention"
        }
        summaryText.text = bad.firstOrNull()?.let { "${it.title} is off — ${it.hint.replaceFirstChar { c -> c.lowercase() }}" } ?: "Managed, locked and reachable."
    }

    private fun relative(at: Long): String {
        val s = ((System.currentTimeMillis() - at) / 1000).coerceAtLeast(0)
        return when {
            s < 60 -> "${s}s ago"
            s < 3600 -> "${s / 60}m ago"
            else -> "${s / 3600}h ago"
        }
    }

    private fun label(s: String): TextView =
        text(s, 11f, FAINT).apply {
            letterSpacing = 0.10f
            setPadding(0, 0, 0, dp(4))
        }

    private fun spacer(): TextView = TextView(this).apply {
        height = dp(16)
    }

    private fun text(
        s: String,
        sizeSp: Float,
        color: Int,
        bold: Boolean = false,
        mono: Boolean = false,
    ): TextView = TextView(this).apply {
        text = s
        setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp)
        setTextColor(color)
        if (bold) setTypeface(typeface, Typeface.BOLD)
        if (mono) typeface = Typeface.MONOSPACE
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    private companion object {
        const val MATCH = ViewGroup.LayoutParams.MATCH_PARENT
        val INK = Color.parseColor("#0E1117")
        val TEXT = Color.parseColor("#E8EEF4")
        val MUTED = Color.parseColor("#8693A4")
        val FAINT = Color.parseColor("#5C6675")
        val SIGNAL = Color.parseColor("#F4B942")
        val OK = Color.parseColor("#3FD08A")
        val ALERT = Color.parseColor("#F2545B")
    }
}
