package com.mdmesh.agent

import android.app.ActivityManager
import android.content.ComponentName
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.InputMethodManager
import android.widget.EditText
import android.widget.FrameLayout
import android.graphics.drawable.GradientDrawable
import android.widget.GridLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.appcompat.app.AlertDialog
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.fragment.app.FragmentActivity
import androidx.core.content.ContextCompat
import androidx.core.graphics.Insets
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.widget.TextViewCompat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.flow.distinctUntilChanged
import com.mdmesh.agent.service.CheckInService
import com.mdmesh.core.action.ResetPasswordTokenStore
import com.mdmesh.core.device.AppInventoryCache
import com.mdmesh.core.device.AppInventoryCollector
import com.mdmesh.core.state.KioskStatusSource
import com.mdmesh.core.store.AdminPasscodeStore
import com.mdmesh.core.store.KioskStateStore
import com.mdmesh.core.telemetry.EventSink
import com.mdmesh.kiosk.CrashLoopGuard
import com.mdmesh.kiosk.KioskController
import com.mdmesh.kiosk.KioskAppKillOverlay
import com.mdmesh.kiosk.KioskEscapeOverlay
import com.mdmesh.kiosk.KioskResult
import com.mdmesh.kiosk.KioskToggles
import com.mdmesh.kiosk.lockTaskFeatures
import com.mdmesh.policy.CapabilityRegistry
import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.ReadableTogglePolicy
import com.mdmesh.policy.devicesettings.AutoBrightnessPolicy
import com.mdmesh.policy.devicesettings.AutoRotationPolicy
import com.mdmesh.policy.devicesettings.FlightModePolicy
import com.mdmesh.policy.wifi.WifiRadioPolicy
import com.mdmesh.policy.wifi.DpmHandle
import com.mdmesh.proto.KioskApplyPayload
import com.mdmesh.proto.PasscodeHash
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject
import kotlin.math.min
import com.mdmesh.agent.ui.BatteryRingView
import com.mdmesh.agent.ui.CountdownRingView
import com.mdmesh.agent.ui.GradientSlider
import com.mdmesh.agent.ui.GroundDrawable
import com.mdmesh.agent.ui.HoldToConfirm
import com.mdmesh.agent.ui.Metrics
import com.mdmesh.agent.ui.ObsidianPrefs
import com.mdmesh.agent.ui.Palette
import com.mdmesh.agent.ui.ShimmerLineView
import com.mdmesh.agent.ui.WifiBarsView
import com.mdmesh.agent.ui.animationsOff
import com.mdmesh.agent.ui.breathe
import com.mdmesh.agent.ui.enter
import com.mdmesh.agent.ui.gradient
import com.mdmesh.agent.ui.gradientText
import com.mdmesh.agent.ui.pressable
import com.mdmesh.agent.ui.rounded
import com.mdmesh.agent.ui.style
import com.mdmesh.agent.ui.withAlpha
import com.mdmesh.agent.ui.loadBrandBitmap
import com.mdmesh.core.store.ClientBrandingStore
import com.mdmesh.core.store.KioskSectionsStore
import com.mdmesh.core.store.LeaderboardRepository
import com.mdmesh.proto.KioskSections

/**
 * MDMesh kiosk HOME. This is the device's persistent launcher (`CATEGORY_HOME`), repointed to
 * by [KioskController.enter] via `addPersistentPreferredActivity`. It renders the last-applied
 * [KioskApplyPayload] persisted in [KioskStateStore]:
 *
 *  - `mode == "single"` → launch + pin the single allowed app ([KioskApplyPayload.pinPackage]).
 *  - `mode == "launcher"` → a themed grid of [KioskApplyPayload.allowedPackages].
 *  - no payload → an idle "managed device" screen (the agent is not in kiosk).
 *
 * Exit affordance is driven by [KioskApplyPayload.exitMode] (`gesture` 7-tap corner / `visible`
 * button / `remote` none) and gated by [KioskApplyPayload.password].
 *
 * A [CrashLoopGuard] protects against a crashing pinned app bouncing back to HOME in a tight
 * loop: each single-app launch registers a fault, and once the loop trips the launcher drops
 * kiosk instead of re-pinning, so a misconfigured deployment cannot brick the device.
 */
@AndroidEntryPoint
class KioskLauncherActivity : FragmentActivity() {

    @Inject lateinit var store: KioskStateStore
    @Inject lateinit var controller: KioskController
    @Inject lateinit var events: EventSink
    @Inject lateinit var crashGuard: CrashLoopGuard
    @Inject lateinit var adminPasscodeStore: AdminPasscodeStore
    @Inject lateinit var dpmHandle: DpmHandle
    @Inject lateinit var resetTokenStore: ResetPasswordTokenStore
    @Inject lateinit var capabilities: CapabilityRegistry
    @Inject lateinit var leaderboardRepo: LeaderboardRepository

    /** Last applied non-null kiosk state, so [onResume] can recover a bounced single-app pin. */
    private var active: KioskApplyPayload? = null

    /** Cached mirror of [AdminPasscodeStore], kept current so [promptExit] can check it
     *  synchronously without blocking on a DataStore read from a dialog callback. */
    private var fleetPasscodeHash: String? = null


    /** The currently-displayed battery/Wi-Fi TextViews, re-pointed by whichever view builder last
     *  ran ([splashView]/[launcherGrid]) so a single timer can keep them live across
     *  [setContentView] swaps without each view needing its own polling loop. Battery sits at the
     *  extreme left, Wi-Fi at the extreme right (beside the kebab menu). */
    private var batteryText: TextView? = null
    private var wifiText: TextView? = null
    private val statusHandler = Handler(Looper.getMainLooper())
    private val statusTick: Runnable = object : Runnable {
        override fun run() {
            updateStatusViews(KioskStatusSource.read(this@KioskLauncherActivity))
            renderLeaderboard()
            statusHandler.postDelayed(this, STATUS_POLL_MS)
        }
    }

    /** Top-center date/time readout, re-pointed by [addStatusBar] like [batteryText]. */
    private var clockText: TextView? = null
    private val clockFormat = SimpleDateFormat("dd MMM yyyy  hh:mm a", Locale.ENGLISH)

    /** Hero-card clock (Obsidian home): "04:45 PM" with a blinking colon, and the full date. */
    private var heroTime: TextView? = null
    private var heroDate: TextView? = null
    private val heroTimeFormat = SimpleDateFormat("hh:mm", Locale.ENGLISH)
    private val heroAmPmFormat = SimpleDateFormat("a", Locale.ENGLISH)
    private val heroDateFormat = SimpleDateFormat("EEEE · dd MMMM yyyy", Locale.ENGLISH)

    /** Live status views of the Obsidian home (re-pointed on every render, like [batteryText]). */
    private var batteryRing: BatteryRingView? = null
    private var batteryPct: TextView? = null
    private var wifiBarsView: WifiBarsView? = null
    private var wifiName: TextView? = null
    private val dockRefreshers = mutableListOf<() -> Unit>()

    /** Sales-leaderboard card on the kiosk home (null on every other screen) and a signature of what
     *  it last drew, so the 30s poll only rebuilds it when something visible changed. */
    private var leaderboardBox: LinearLayout? = null
    private var leaderboardSig: String? = null
    /** The admin switched a kiosk section on/off in the console: redraw whichever screen is showing. */
    private val sectionsListener = android.content.SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
        if (key == KioskSectionsStore.KEY_VERSION) runOnUiThread {
            val p = active
            if (p == null) setContentView(idleView()) else if (p.mode != "single") setContentView(launcherGrid(p))
        }
    }

    private fun sections(): KioskSections = KioskSectionsStore.read(this)

    /** Client branding as the admin wants it shown: the name always, the logo only if its section is on. */
    private fun brand(): ClientBrandingStore.Branding =
        ClientBrandingStore.read(this).let { b -> if (sections().clientLogo) b else b.copy(logo = null, mark = null) }

    private val leaderboardListener = android.content.SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
        if (key == LeaderboardRepository.KEY_VERSION) runOnUiThread { renderLeaderboard() }
    }

    /** Re-renders as soon as a new client logo/name lands (check-in runs in the service). Held in
     *  a field: SharedPreferences keeps listeners weakly. */
    private val brandingListener = android.content.SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
        if (key == ClientBrandingStore.KEY_VERSION) runOnUiThread {
            val p = active
            if (p == null) setContentView(idleView()) else if (p.mode != "single") setContentView(launcherGrid(p))
        }
    }

    /** Updates the clock once a second (the hero colon blinks), aligned to the second boundary
     *  so it never drifts. */
    private val clockTick: Runnable = object : Runnable {
        override fun run() {
            renderClock()
            val now = System.currentTimeMillis()
            statusHandler.postDelayed(this, 1_000L - now % 1_000L + 20L)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // A kiosk device boots straight into HOME (this); keep the command channel alive even if
        // the user never opens the status screen.
        ContextCompat.startForegroundService(this, Intent(this, CheckInService::class.java))
        setContentView(idleView())
        // React to kiosk.enter/kiosk.exit live: those run in the check-in service, not here, so we
        // observe the persisted state and re-render (enter → grid/pin, exit → unpin + idle) without
        // waiting for the user to touch the screen.
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                store.flow().distinctUntilChanged().collect(::applyState)
            }
        }
        lifecycleScope.launch {
            val current = store.load()
            if (current == null && dpmHandle.dpm.isDeviceOwnerApp(packageName)) {
                val fallback = store.loadLastKnown() ?: defaultKioskPayload()
                store.save(fallback)
            }
        }
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                adminPasscodeStore.flow().distinctUntilChanged().collect { fleetPasscodeHash = it }
            }
        }
        statusHandler.post(statusTick)
        ClientBrandingStore.prefs(this).registerOnSharedPreferenceChangeListener(brandingListener)
        LeaderboardRepository.prefs(this).registerOnSharedPreferenceChangeListener(leaderboardListener)
        KioskSectionsStore.prefs(this).registerOnSharedPreferenceChangeListener(sectionsListener)
        // Live sales leaderboard: poll every 30s, only while the kiosk home is on screen and only
        // when its card exists. A failed poll keeps showing the last good copy.
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                while (true) {
                    if (leaderboardBox != null) leaderboardRepo.refresh()
                    kotlinx.coroutines.delay(LEADERBOARD_POLL_MS)
                }
            }
        }
    }

    override fun onStart() {
        super.onStart()
        // Restart on every return to the foreground so the clock is right immediately (and picks up
        // any time/timezone change made while hidden), instead of waiting for the next minute.
        statusHandler.removeCallbacks(clockTick)
        statusHandler.post(clockTick)
    }

    override fun onStop() {
        statusHandler.removeCallbacks(clockTick)
        super.onStop()
    }

    override fun onDestroy() {
        ClientBrandingStore.prefs(this).unregisterOnSharedPreferenceChangeListener(brandingListener)
        LeaderboardRepository.prefs(this).unregisterOnSharedPreferenceChangeListener(leaderboardListener)
        KioskSectionsStore.prefs(this).unregisterOnSharedPreferenceChangeListener(sectionsListener)
        statusHandler.removeCallbacks(statusTick)
        statusHandler.removeCallbacks(clockTick)
        super.onDestroy()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        active?.let {
            startLockTaskSafely()
            applyState(it)
        }
    }

    override fun onResume() {
        super.onResume()
        // A single-app pin that returned us to HOME means the pinned app exited or crashed — re-pin
        // it (counting the bounce so a crash loop trips the guard). Enter/exit transitions are
        // handled by the flow collector, not here.
        val p = active ?: return
        startLockTaskSafely()
        if (p.mode == "single") {
            crashGuard.registerFault()
            if (bailOnCrashLoop()) return
            launchPinned(p)
        } else {
            // Grid mode: being resumed means whatever app was open just exited/backgrounded to
            // HOME, so there's no "current app" for the kill button to target anymore.
            KioskAppKillOverlay.hide()
        }
    }


    private fun applyState(p: KioskApplyPayload?) {
        active = p
        setWatchdogArmed(p != null)
        if (p == null) {
            stopLockTaskSafely()
            KioskAppKillOverlay.hide()
            setContentView(idleView())
            return
        }
        if (bailOnCrashLoop()) return
        promptDefaultHomeIfNeeded()
        // Use controller.enter() to set DPM lock-task allowlist, features, and persistent HOME,
        // and startLockTaskSafely() to actually place this Activity into lock task mode.
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
        controller.enter(ComponentName(this, HOME_ALIAS), allowed, features)
        startLockTaskSafely()
        if (p.mode == "single" && p.pinPackage != null) {
            launchPinned(p)
        } else {
            setContentView(launcherGrid(p))
        }
    }

    /** Launch + show the pinned app (single mode), with a themed splash behind it. */
    private fun launchPinned(p: KioskApplyPayload) {
        val pkg = p.pinPackage ?: return setContentView(launcherGrid(p))
        val intent = packageManager.getLaunchIntentForPackage(pkg)
        if (intent == null) {
            setContentView(launcherGrid(p)) // unknown package → fall back to the grid
            return
        }
        setContentView(splashView(p))
        runCatching { startActivity(intent) }
        // Ungated self-service kill switch (explicit request, 2026-09-20): staff need a way to
        // force-stop + relaunch a frozen pinned app on the spot, without the admin PIN and without
        // exiting kiosk mode entirely. See killAndRelaunchPinnedApp()'s doc comment for the
        // self-protection guard.
        KioskAppKillOverlay.show(this) { killAndRelaunchPinnedApp(pkg) }
    }

    /** Force-stops [pkg] (via a suspend/unsuspend pulse -- same primitive as the console's remote
     *  `device.appKill`, see `AppKillHandler`'s doc comment for why: a Device Owner has no public
     *  `forceStopPackage` API, but suspending a package stops its process immediately, and
     *  un-suspending right after leaves it killed but freely launchable again) then relaunches it.
     *  Hard-refuses to ever target this agent's own package, mirroring `AppKillHandler`'s guard --
     *  [pkg] should never legitimately be us (we're never our own pinned app), but this stays a
     *  correctness invariant, not an assumption. */
    private fun killAndRelaunchPinnedApp(pkg: String) {
        if (pkg == packageName) return
        runCatching {
            val packages = arrayOf(pkg)
            dpmHandle.dpm.setPackagesSuspended(dpmHandle.admin, packages, true)
            dpmHandle.dpm.setPackagesSuspended(dpmHandle.admin, packages, false)
        }
        toastShort("Relaunching…")
        runCatching {
            packageManager.getLaunchIntentForPackage(pkg)?.let { startActivity(it) }
        }
    }

    /** @return true if a crash loop tripped (kiosk dropped + recovery shown), so the caller stops. */
    private fun bailOnCrashLoop(): Boolean {
        if (!crashGuard.isCrashLoopDetected()) return false
        events.record("kioskCrashLoop", "dropped kiosk after repeated crashes")
        // Disarm BEFORE stopLockTaskSafely()/controller.exit() below — the watchdog reacts to
        // lockTaskModeState going to NONE, and without this it would misread our own
        // intentional crash-loop exit as an escape and immediately relaunch us right back in.
        setWatchdogArmed(false)
        // Safety net: clear a stale KioskEscapeOverlay in case this bail fires mid-escape,
        // right as the watchdog happened to have one showing.
        KioskEscapeOverlay.hide()
        stopLockTaskSafely()
        controller.exit()
        active = null
        lifecycleScope.launch { store.save(null) }
        setContentView(recoveryView())
        return true
    }

    /** Enables/disables [com.mdmesh.kiosk.KioskWatchdogService] — a no-op on a Device-Owner
     *  device (the real lock-task path has no escape gesture to watch for; arming it there would
     *  just be an unused accessibility surface enabled for nothing). Only meaningful for the
     *  Lite (Device Admin only) tier's [com.mdmesh.kiosk.SoftPinKioskController]. */
    private fun setWatchdogArmed(armed: Boolean) {
        if (dpmHandle.dpm.isDeviceOwnerApp(packageName)) return
        // Set/clear the in-process suppression flag BEFORE touching the component's enabled
        // state — see KioskWatchdogService.suppressed's doc comment for why the component-enabled
        // flag alone loses a race against an already-running service instance.
        if (!armed) {
            com.mdmesh.kiosk.KioskWatchdogService.suppressed = true
        }
        runCatching {
            val state = if (armed) {
                android.content.pm.PackageManager.COMPONENT_ENABLED_STATE_ENABLED
            } else {
                android.content.pm.PackageManager.COMPONENT_ENABLED_STATE_DISABLED
            }
            packageManager.setComponentEnabledSetting(
                ComponentName(this, "com.mdmesh.kiosk.KioskWatchdogService"),
                state,
                android.content.pm.PackageManager.DONT_KILL_APP,
            )
        }
        if (armed) {
            com.mdmesh.kiosk.KioskWatchdogService.suppressed = false
        }
    }

    /** Lite mode (no Device-Owner) cannot force itself to become the default home app — Android
     *  requires the user to pick it manually. Without this, "Enter Kiosk" silently does nothing
     *  visible: lock task still starts, but pressing Home just falls through to whatever launcher
     *  was already set as default. Detect that gap and send the user straight to the picker. */
    private fun promptDefaultHomeIfNeeded() {
        if (dpmHandle.dpm.isDeviceOwnerApp(packageName)) return // Device-Owner path forces this itself.
        val home = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME)
        val resolved = packageManager.resolveActivity(home, android.content.pm.PackageManager.MATCH_DEFAULT_ONLY)
        if (resolved?.activityInfo?.packageName == packageName) return // Already the default home app.
        alert()
            .setTitle("One-time setup needed")
            .setMessage(
                "To lock this device, Android needs AMBIC MDM set as the Home app.\n\n" +
                    "Tap Continue, then choose AMBIC MDM and set it as default.",
            )
            .setCancelable(false)
            .setPositiveButton("Continue") { _, _ ->
                runCatching { startActivity(Intent(android.provider.Settings.ACTION_HOME_SETTINGS)) }
            }
            .show()
    }

    private fun startLockTaskSafely() {
        runCatching {
            val am = getSystemService(ActivityManager::class.java)
            if (am?.lockTaskModeState == android.app.ActivityManager.LOCK_TASK_MODE_NONE) startLockTask()
        }
    }

    private fun stopLockTaskSafely() {
        runCatching {
            val am = getSystemService(ActivityManager::class.java)
            if (am?.lockTaskModeState != android.app.ActivityManager.LOCK_TASK_MODE_NONE) stopLockTask()
        }
    }

    // --- Exit flow ---------------------------------------------------------------------------

    /**
     * Whether the header shows the ⋮ admin menu button. A "visible" kiosk always does; a "gesture" kiosk does too, as long as
     * an exit password or fleet passcode exists, because without one a tap would leave kiosk with no check. A "remote"-only
     * kiosk never offers an on-device exit.
     */
    private fun showAdminMenuButton(p: KioskApplyPayload): Boolean = when (p.exitMode) {
        "remote" -> false
        "visible" -> true
        else -> !p.password.isNullOrBlank() || !fleetPasscodeHash.isNullOrBlank()
    }

    private fun promptExit(p: KioskApplyPayload) {
        val pw = p.password
        val fleetHash = fleetPasscodeHash
        if (pw.isNullOrBlank() && fleetHash.isNullOrBlank()) {
            doExit()
            return
        }
        if (biometricAvailable()) {
            promptBiometric(p, onUnavailableOrDeclined = { promptPasscode(p) })
        } else {
            promptPasscode(p)
        }
    }

    /** True only when this device has enrolled, working biometrics right now — never device
     *  credential (PIN/pattern), which would just be a second way to bypass our own passcode. */
    private fun biometricAvailable(): Boolean =
        BiometricManager.from(this).canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG) ==
            BiometricManager.BIOMETRIC_SUCCESS

    /** Fast path only — the fleet/session passcode ([promptPasscode]) stays the source of truth an
     *  admin can always fall back to, since biometrics are enrolled per-device with no console
     *  visibility or remote revocation. Any outcome other than success (declined, error, no match
     *  configured) falls through to the passcode dialog rather than dead-ending the admin. */
    private fun promptBiometric(p: KioskApplyPayload, onUnavailableOrDeclined: () -> Unit) {
        val prompt = BiometricPrompt(
            this,
            ContextCompat.getMainExecutor(this),
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    showAdminMenu(p)
                }
                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    onUnavailableOrDeclined()
                }
                override fun onAuthenticationFailed() = Unit // let the prompt's own retry UI handle it
            },
        )
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Admin access")
            .setSubtitle("Use face or fingerprint unlock")
            .setNegativeButtonText("Use passcode instead")
            .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG)
            .build()
        prompt.authenticate(info)
    }

    private fun promptPasscode(p: KioskApplyPayload) {
        val pw = p.password
        val fleetHash = fleetPasscodeHash
        val pal = palette(p)
        val m = Metrics(this)
        sheet(pal, m, "Admin access", null, "Enter the admin passcode to open the admin menu.") { body, dialog ->
            val input = EditText(this).apply {
                inputType = android.text.InputType.TYPE_CLASS_TEXT or
                    android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
                hint = "Admin passcode"
                setHintTextColor(pal.faint)
                style(m.sp(16f), pal.text, 500)
                setPadding(m.dp(16), m.dp(14), m.dp(16), m.dp(14))
                background = rounded(pal.surface2, m.dp(14f), pal.line, m.dp(1))
                layoutParams = LinearLayout.LayoutParams(MATCH, ViewGroup.LayoutParams.WRAP_CONTENT)
                setOnFocusChangeListener { v, focused ->
                    v.background = rounded(pal.surface2, m.dp(14f), if (focused) pal.c1 else pal.line, m.dp(if (focused) 2 else 1))
                }
            }
            val error = TextView(this).apply {
                style(m.sp(12f), pal.alert, 500)
                setPadding(m.dp(4), m.dp(8), 0, 0)
                visibility = View.GONE
            }
            fun submit() {
                val entered = input.text.toString()
                // Either the per-session password or the fleet-wide admin passcode (set from the
                // web console's Settings page, delivered on check-in) unlocks the admin menu.
                val sessionMatch = pw != null && entered == pw
                val fleetMatch = !fleetHash.isNullOrBlank() && PasscodeHash.matches(entered, fleetHash)
                if (sessionMatch || fleetMatch) {
                    dialog.dismiss()
                    showAdminMenu(p)
                } else {
                    error.text = "That passcode isn't right. Try again."
                    error.visibility = View.VISIBLE
                    input.text.clear()
                    input.animate().translationX(m.dp(8f)).setDuration(50).withEndAction {
                        input.animate().translationX(0f).setDuration(120).start()
                    }.start()
                }
            }
            input.setOnEditorActionListener { _, _, _ -> submit(); true }
            body.addView(input)
            body.addView(error)
            val buttons = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(0, m.dp(16), 0, 0)
            }
            buttons.addView(
                TextView(this).apply {
                    text = "Cancel"
                    gravity = Gravity.CENTER
                    style(m.sp(14f), pal.text, 600)
                    background = rounded(pal.surface2, m.dp(14f), pal.line, m.dp(1))
                    layoutParams = LinearLayout.LayoutParams(0, m.dp(48), 1f).apply { rightMargin = m.dp(10) }
                    setOnClickListener { dialog.dismiss() }
                    pressable()
                },
            )
            buttons.addView(
                TextView(this).apply {
                    text = "Continue"
                    gravity = Gravity.CENTER
                    style(m.sp(14f), Color.WHITE, 700)
                    background = gradient(intArrayOf(pal.c1, pal.c2), m.dp(14f))
                    layoutParams = LinearLayout.LayoutParams(0, m.dp(48), 1f)
                    setOnClickListener { submit() }
                    pressable()
                },
            )
            body.addView(buttons)
            dialog.window?.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_STATE_VISIBLE or
                android.view.WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
            input.requestFocus()
        }
    }

    // --- Admin menu ---------------------------------------------------------------------------
    //
    // Everything below is gated behind the same passcode check as kiosk exit (promptExit, above)
    // — reachable only after a correct session/fleet passcode, exactly like exit itself. None of
    // these screens (Settings, a browser, the wallpaper picker) are in the kiosk's own allowlist
    // (KioskApplyPayload.allowedPackages — what actually shows as icons to the end user), so lock
    // task mode would otherwise silently refuse to launch them. launchAllowlisted() resolves the
    // real target package for a given intent and extends the lock-task allowlist to include it
    // (additive, never removes the admin-configured apps) before starting it.

    private class AdminItem(val glyph: String, val label: String, val trailing: String?, val action: () -> Unit, val icon: Int? = null)

    /** Admin menu as a grouped sheet. Destructive actions sit in a red Danger zone and need a
     *  press-and-hold, so a stray tap can never exit kiosk or start an uninstall. */
    private fun showAdminMenu(p: KioskApplyPayload) {
        val pal = palette(p)
        val m = Metrics(this)
        val version = runCatching { packageManager.getPackageInfo(packageName, 0).versionName }.getOrNull()
        val ssid = KioskStatusSource.read(this).ssid
        val appearance = when (ObsidianPrefs.appearance(this)) { "light" -> "Light"; "system" -> "System"; else -> "Dark" }
        sheet(pal, m, "Admin", "PASSCODE VERIFIED", null) { body, dialog ->
            fun go(a: () -> Unit): () -> Unit = { dialog.dismiss(); a() }
            adminGroup(body, pal, m, "APPS & HOME", 0, listOf(
                AdminItem("▦", "Manage apps", null, go { manageAppsDialog(p) }),
                AdminItem("★", "Set default application", null, go {
                    launchAllowlisted(Intent(android.provider.Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS))
                }),
                AdminItem("▣", "Change background", null, go { launchAllowlisted(Intent(Intent.ACTION_SET_WALLPAPER)) }),
            ))
            adminGroup(body, pal, m, "BROWSER & INPUT", 1, listOf(
                AdminItem("↗", "Browser shortcuts", null, go { openBrowser() }),
                AdminItem("⚙", "Browser settings", null, go { openBrowserSettings() }),
                AdminItem("⌨", "Capital Keyboard settings", null, go { showKeyboardSettingsDialog() }),
                AdminItem("Aa", "Accessibility / Auto-Caps", null, go {
                    launchAllowlisted(Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS))
                }),
            ))
            adminGroup(body, pal, m, "DEVICE", 2, listOf(
                AdminItem("", "Configure Wi-Fi", ssid, go {
                    launchAllowlisted(Intent(android.provider.Settings.ACTION_WIFI_SETTINGS))
                }, R.drawable.ic_ob_wifi),
                AdminItem("⚙", "Open system settings", null, go {
                    launchAllowlisted(Intent(android.provider.Settings.ACTION_SETTINGS))
                }),
                AdminItem("#", "Reset device passcode", null, go { promptResetPasscode() }),
                AdminItem("", "Appearance", appearance, go { chooseAppearance(p) }, R.drawable.ic_ob_adaptive),
                AdminItem("ⓘ", "About AMBIC MDM", version, go { showAbout() }),
            ))
            // Danger zone: hold-to-confirm rows.
            body.addView(groupLabel(pal, m, "DANGER ZONE", pal.alert))
            val danger = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                background = rounded(withAlpha(pal.alert, 0.06f), m.dp(16f), withAlpha(pal.alert, 0.35f), m.dp(1))
                clipToOutline = true
                enter(180)
            }
            danger.addView(holdRow(pal, m, "↩", "Hold to exit kiosk") { dialog.dismiss(); doExit() })
            danger.addView(divider(pal, m))
            danger.addView(holdRow(pal, m, "✕", "Hold to uninstall AMBIC MDM") { dialog.dismiss(); confirmUninstall() })
            body.addView(danger)
        }
    }

    private fun groupLabel(pal: Palette, m: Metrics, label: String, color: Int = pal.muted): TextView =
        TextView(this).apply {
            text = label
            style(m.sp(10f), color, 700, mono = true, letterSp = 0.18f)
            setPadding(m.dp(6), m.dp(14), 0, m.dp(6))
        }

    private fun divider(pal: Palette, m: Metrics): View = View(this).apply {
        setBackgroundColor(pal.line)
        layoutParams = LinearLayout.LayoutParams(MATCH, m.dp(1))
    }

    private fun adminGroup(body: LinearLayout, pal: Palette, m: Metrics, title: String, index: Int, items: List<AdminItem>) {
        body.addView(groupLabel(pal, m, title))
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded(pal.surface2, m.dp(16f), pal.line, m.dp(1))
            clipToOutline = true
            enter(index * 60L)
        }
        items.forEachIndexed { i, item ->
            if (i > 0) card.addView(divider(pal, m))
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(m.dp(12), m.dp(11), m.dp(14), m.dp(11))
                isClickable = true
                background = android.graphics.drawable.RippleDrawable(
                    android.content.res.ColorStateList.valueOf(withAlpha(pal.c1, 0.18f)), null, null,
                )
                setOnClickListener { item.action() }
            }
            val iconBox = FrameLayout(this).apply {
                background = rounded(withAlpha(pal.c1, 0.12f), m.dp(9f))
                layoutParams = LinearLayout.LayoutParams(m.dp(30), m.dp(30)).apply { rightMargin = m.dp(12) }
            }
            if (item.icon != null) {
                iconBox.addView(
                    ImageView(this).apply { setImageResource(item.icon); setColorFilter(pal.c1) },
                    FrameLayout.LayoutParams(m.dp(17), m.dp(17), Gravity.CENTER),
                )
            } else {
                iconBox.addView(
                    TextView(this).apply { text = item.glyph; gravity = Gravity.CENTER; style(m.sp(12f), pal.c1, 700) },
                    FrameLayout.LayoutParams(MATCH, MATCH),
                )
            }
            row.addView(iconBox)
            row.addView(
                TextView(this).apply {
                    text = item.label
                    style(m.sp(14f), pal.text, 500)
                    layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                },
            )
            row.addView(
                TextView(this).apply {
                    text = item.trailing ?: "›"
                    style(m.sp(if (item.trailing == null) 18f else 12f), pal.muted, 500, mono = item.trailing != null)
                    maxLines = 1
                },
            )
            card.addView(row)
        }
        body.addView(card)
    }

    private fun holdRow(pal: Palette, m: Metrics, glyph: String, label: String, onConfirm: () -> Unit): View =
        HoldToConfirm(this, pal, onConfirm = onConfirm).apply {
            text = "$glyph   $label"
            style(m.sp(14f), pal.alert, 600)
            setPadding(m.dp(16), m.dp(14), m.dp(16), m.dp(14))
            layoutParams = LinearLayout.LayoutParams(MATCH, ViewGroup.LayoutParams.WRAP_CONTENT)
        }

    /** Dark / Light / System for the on-device screens; re-renders the kiosk home immediately. */
    private fun chooseAppearance(p: KioskApplyPayload) {
        val modes = arrayOf("dark", "light", "system")
        val labels = arrayOf("Dark", "Light", "Follow system")
        val current = modes.indexOf(ObsidianPrefs.appearance(this)).coerceAtLeast(0)
        alert()
            .setTitle("Appearance")
            .setSingleChoiceItems(labels, current) { d, which ->
                ObsidianPrefs.setAppearance(this, modes[which])
                d.dismiss()
                if (active != null) setContentView(launcherGrid(p)) else setContentView(idleView())
            }
            .setNegativeButton("Close", null)
            .show()
    }

    /** AlertDialog themed to the current appearance (dark dialogs on a dark kiosk). */
    private fun alert(): AlertDialog.Builder = AlertDialog.Builder(
        this,
        if (ObsidianPrefs.isDark(this)) androidx.appcompat.R.style.Theme_AppCompat_Dialog_Alert
        else androidx.appcompat.R.style.Theme_AppCompat_Light_Dialog_Alert,
    )

    private fun showKeyboardSettingsDialog() {
        val options = arrayOf(
            "1. Enable AMBIC Keyboard (Settings)",
            "2. Switch active keyboard to AMBIC",
            "3. Lock to AMBIC Keyboard only (Device Owner)",
            "4. Allow all keyboards (Unlock)",
        )
        alert()
            .setTitle("Capital Keyboard settings")
            .setItems(options) { _, which ->
                when (which) {
                    0 -> launchAllowlisted(Intent(android.provider.Settings.ACTION_INPUT_METHOD_SETTINGS))
                    1 -> {
                        val imm = getSystemService(InputMethodManager::class.java)
                        imm?.showInputMethodPicker()
                    }
                    2 -> {
                        if (dpmHandle.dpm.isDeviceOwnerApp(packageName)) {
                            val success = runCatching {
                                dpmHandle.dpm.setPermittedInputMethods(
                                    dpmHandle.admin,
                                    listOf(packageName)
                                )
                            }.isSuccess
                            val msg = if (success) "Locked to AMBIC Keyboard only." else "Failed to lock input methods."
                            Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
                            val imm = getSystemService(InputMethodManager::class.java)
                            imm?.showInputMethodPicker()
                        } else {
                            Toast.makeText(this, "Device Owner required to restrict keyboards.", Toast.LENGTH_SHORT).show()
                        }
                    }
                    3 -> {
                        if (dpmHandle.dpm.isDeviceOwnerApp(packageName)) {
                            runCatching {
                                dpmHandle.dpm.setPermittedInputMethods(
                                    dpmHandle.admin,
                                    null
                                )
                            }
                            Toast.makeText(this, "All keyboards allowed.", Toast.LENGTH_SHORT).show()
                        }
                    }
                }
            }
            .setNegativeButton("Close", null)
            .show()
    }

    /**
     * Ungated Quick Controls entry for screens without the dock (idle view): a glass pill in the
     * bottom-end corner. Deliberately separate from [showAdminMenu] — that menu is passcode-gated
     * for IT, while these are harmless everyday comfort toggles a kiosk operator needs constantly,
     * and nothing here ever opens the real Settings app.
     *
     * Shows nothing if not one of the supported policies is available on this device (e.g. the
     * WRITE_SETTINGS appop was never granted for rotation): an absent capability means an absent
     * button, not a dead one.
     */
    private fun addQuickControlsAffordance(parent: ViewGroup) {
        if (!sections().quickControls || !quickControlsAvailable()) return
        val pal = palette(active)
        val m = Metrics(this)
        val button = TextView(this).apply {
            text = "Quick Controls"
            style(m.sp(12f), pal.text, 600)
            setPadding(m.dp(16), m.dp(10), m.dp(16), m.dp(10))
            background = rounded(pal.glass, m.dp(20f), pal.line, m.dp(1))
            setOnClickListener { showQuickControlsDialog() }
            pressable()
        }
        parent.addView(FrameWrap(this, button, Gravity.BOTTOM or Gravity.END, m.dp(16), avoidSystemBars = true))
    }

    private fun quickControlsAvailable(): Boolean {
        if (!::capabilities.isInitialized) return false
        return capabilities.togglePolicies().keys.any {
            it in setOf(
                AutoRotationPolicy.CAPABILITY_KEY,
                AutoBrightnessPolicy.CAPABILITY_KEY,
                FlightModePolicy.CAPABILITY_KEY,
                WifiRadioPolicy.CAPABILITY_KEY,
            )
        } || capabilities.brightnessLevelPolicy() != null
    }

    private fun toggleState(key: String): Boolean? =
        (capabilities.togglePolicies()[key] as? ReadableTogglePolicy)?.isEnabled()

    /** Applies one Quick Control, logs it for the console timeline, and remembers when Wi-Fi was
     *  switched off (for the auto-restore countdown). Returns false (with a toast) on failure. */
    private fun applyToggle(key: String, label: String, checked: Boolean): Boolean {
        val policy = capabilities.togglePolicies()[key] as? ReadableTogglePolicy ?: return false
        val outcome = policy.setEnabled(checked)
        if (outcome !is PolicyOutcome.Applied) {
            Toast.makeText(this, "Could not change $label.", Toast.LENGTH_SHORT).show()
            return false
        }
        runCatching { events.record("quickControl", "$key=${if (checked) "on" else "off"}") }
        if (key == WifiRadioPolicy.CAPABILITY_KEY) {
            uiPrefs().edit().putLong(PREF_WIFI_OFF_AT, if (checked) 0L else System.currentTimeMillis()).apply()
        }
        return true
    }

    /** Flips the tablet UI between Dark and Light and re-draws the kiosk home in the new palette. */
    private fun appearanceTile(pal: Palette, m: Metrics, dialog: android.app.Dialog): View {
        val dark = ObsidianPrefs.isDark(this)
        val tile = FrameLayout(this).apply {
            layoutParams = GridLayout.LayoutParams(
                GridLayout.spec(GridLayout.UNDEFINED, 1f),
                GridLayout.spec(GridLayout.UNDEFINED, 1f),
            ).apply {
                width = 0
                setMargins(m.dp(4), m.dp(4), m.dp(4), m.dp(4))
            }
            background = rounded(pal.surface2, m.dp(18f), pal.line, m.dp(1))
            contentDescription = "Switch to ${if (dark) "light" else "dark"} mode"
            pressable()
        }
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(m.dp(12), m.dp(12), m.dp(12), m.dp(12))
        }
        val icon = FrameLayout(this).apply {
            background = rounded(withAlpha(pal.text, 0.08f), m.dp(11f))
            layoutParams = LinearLayout.LayoutParams(m.dp(36), m.dp(36)).apply { bottomMargin = m.dp(8) }
        }
        icon.addView(
            ImageView(this).apply {
                setImageResource(if (dark) R.drawable.ic_ob_moon else R.drawable.ic_ob_sun)
                setColorFilter(pal.text)
            },
            FrameLayout.LayoutParams(m.dp(20), m.dp(20), Gravity.CENTER),
        )
        col.addView(icon)
        col.addView(TextView(this).apply { text = "Appearance"; style(m.sp(13f), pal.text, 700) })
        col.addView(TextView(this).apply { text = if (dark) "Dark" else "Light"; style(m.sp(11.5f), pal.muted) })
        tile.addView(col)
        tile.setOnClickListener {
            ObsidianPrefs.setAppearance(this, if (dark) "light" else "dark")
            dialog.dismiss()
            val p = active
            if (p == null) setContentView(idleView()) else if (p.mode != "single") setContentView(launcherGrid(p))
            showQuickControlsDialog() // reopen in the new palette so the change is visible at once
        }
        return tile
    }

    private fun iconRes(key: String): Int = when (key) {
        AutoRotationPolicy.CAPABILITY_KEY -> R.drawable.ic_ob_rotate
        AutoBrightnessPolicy.CAPABILITY_KEY -> R.drawable.ic_ob_adaptive
        WifiRadioPolicy.CAPABILITY_KEY -> R.drawable.ic_ob_wifi
        FlightModePolicy.CAPABILITY_KEY -> R.drawable.ic_ob_flight
        else -> R.drawable.ic_ob_more
    }

    private fun iconView(res: Int, tint: Int, sizePx: Int): ImageView = ImageView(this).apply {
        setImageResource(res)
        setColorFilter(tint)
        layoutParams = LinearLayout.LayoutParams(sizePx, sizePx)
    }

    private fun uiPrefs() = getSharedPreferences("obsidian_ui", MODE_PRIVATE)

    /** Millis Wi-Fi was switched off from here, or 0 when on / unknown / restore window passed. */
    private fun wifiOffAt(): Long {
        val at = uiPrefs().getLong(PREF_WIFI_OFF_AT, 0L)
        return if (at > 0 && System.currentTimeMillis() - at < WifiRadioPolicy.AUTO_RESTORE_MS) at else 0L
    }

    /** Quick Controls as a bottom sheet of big toggle tiles + a gradient brightness bar. One tile
     *  per supported policy; unsupported ones are simply absent, not disabled. */
    private fun showQuickControlsDialog() {
        val pal = palette(active)
        val m = Metrics(this)
        val toggles = capabilities.togglePolicies()
        val who = active?.deviceLabel?.takeIf { it.isNotBlank() } ?: "This device"
        sheet(pal, m, "Quick Controls", null, "$who · changes are logged to the console") { body, dialog ->
            val grid = GridLayout(this).apply {
                columnCount = if (m.isPhone) 3 else 4
                layoutParams = LinearLayout.LayoutParams(MATCH, ViewGroup.LayoutParams.WRAP_CONTENT)
            }
            val specs = listOf(
                Triple(AutoRotationPolicy.CAPABILITY_KEY, "Auto-rotate", "⟳"),
                Triple(AutoBrightnessPolicy.CAPABILITY_KEY, "Adaptive", "◐"),
                Triple(WifiRadioPolicy.CAPABILITY_KEY, "Wi-Fi", "◠"),
                Triple(FlightModePolicy.CAPABILITY_KEY, "Flight mode", "✈"),
            )
            specs.filter { toggles[it.first] is ReadableTogglePolicy }.forEachIndexed { i, (key, label, glyph) ->
                grid.addView(controlTile(pal, m, key, label, glyph).apply { enter(i * 50L) })
            }
            // Light / Dark for the tablet's own screens; needs no passcode, like the other tiles.
            grid.addView(appearanceTile(pal, m, dialog).apply { enter(250) })
            body.addView(grid)

            capabilities.brightnessLevelPolicy()?.let { brightness ->
                val level = brightness.getLevel()
                body.addView(
                    TextView(this).apply {
                        text = "Brightness"
                        style(m.sp(13f), pal.muted, 600)
                        setPadding(m.dp(4), m.dp(14), 0, m.dp(8))
                    },
                )
                body.addView(
                    GradientSlider(this, pal).apply {
                        value = level ?: 50
                        isEnabled = level != null
                        onChange = { brightness.setLevel(it) }
                        // One log entry per drag, not per move.
                        onCommit = { runCatching { events.record("quickControl", "brightness=$it%") } }
                        layoutParams = LinearLayout.LayoutParams(MATCH, m.dp(46))
                    },
                )
            }

            if (toggles.containsKey(WifiRadioPolicy.CAPABILITY_KEY)) {
                val note = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    setPadding(m.dp(4), m.dp(14), 0, 0)
                }
                note.addView(
                    View(this).apply {
                        background = rounded(pal.c3, m.dp(4f))
                        layoutParams = LinearLayout.LayoutParams(m.dp(7), m.dp(7)).apply { rightMargin = m.dp(8) }
                        breathe(1200)
                    },
                )
                note.addView(
                    TextView(this).apply {
                        text = "Wi-Fi turns itself back on 3 minutes after you switch it off."
                        style(m.sp(12f), pal.muted)
                    },
                )
                body.addView(note)
            }
            dialog.setOnDismissListener { refreshDock() }
        }
    }

    /** One big Quick Controls tile. Tapping flips it; Wi-Fi shows a countdown ring while off. */
    private fun controlTile(pal: Palette, m: Metrics, key: String, label: String, glyph: String): View {
        val tile = FrameLayout(this).apply {
            layoutParams = GridLayout.LayoutParams(
                GridLayout.spec(GridLayout.UNDEFINED, 1f),
                GridLayout.spec(GridLayout.UNDEFINED, 1f),
            ).apply {
                width = 0
                setMargins(m.dp(4), m.dp(4), m.dp(4), m.dp(4))
            }
            pressable()
        }
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(m.dp(12), m.dp(12), m.dp(12), m.dp(12))
        }
        val icon = FrameLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(m.dp(36), m.dp(36)).apply { bottomMargin = m.dp(8) }
        }
        val iconImg = ImageView(this).apply { setImageResource(iconRes(key)) }
        icon.addView(iconImg, FrameLayout.LayoutParams(m.dp(20), m.dp(20), Gravity.CENTER))
        val title = TextView(this).apply { text = label; style(m.sp(13f), pal.text, 700) }
        val state = TextView(this).apply { style(m.sp(11.5f), pal.muted) }
        col.addView(icon); col.addView(title); col.addView(state)
        tile.addView(col)
        val ring = CountdownRingView(this, pal).apply { totalMs = WifiRadioPolicy.AUTO_RESTORE_MS }
        tile.addView(ring, FrameLayout.LayoutParams(m.dp(22), m.dp(22), Gravity.TOP or Gravity.END).apply {
            setMargins(0, m.dp(10), m.dp(10), 0)
        })
        val countdown = object : Runnable {
            override fun run() {
                val off = wifiOffAt()
                if (off == 0L) return
                val left = ((WifiRadioPolicy.AUTO_RESTORE_MS - (System.currentTimeMillis() - off)) / 1000).coerceAtLeast(0)
                state.text = "Back in %d:%02d".format(left / 60, left % 60)
                tile.postDelayed(this, 1000)
            }
        }

        fun render() {
            val on = toggleState(key)
            val isOn = on == true
            tile.background = if (isOn) {
                gradient(intArrayOf(withAlpha(pal.c1, 0.22f), withAlpha(pal.c2, 0.18f)), m.dp(18f)).apply {
                    setStroke(m.dp(1), withAlpha(pal.c1, 0.55f))
                }
            } else rounded(pal.surface2, m.dp(18f), pal.line, m.dp(1))
            icon.background = if (isOn) gradient(intArrayOf(pal.c1, pal.c2), m.dp(11f))
            else rounded(withAlpha(pal.text, 0.08f), m.dp(11f))
            iconImg.setColorFilter(if (isOn) Color.WHITE else pal.text)
            state.text = when (on) { null -> "Unavailable"; true -> "On"; false -> "Off" }
            val showRing = key == WifiRadioPolicy.CAPABILITY_KEY && !isOn && wifiOffAt() > 0
            ring.visibility = if (showRing) View.VISIBLE else View.GONE
            tile.removeCallbacks(countdown)
            if (showRing) { ring.startedAt = wifiOffAt(); tile.post(countdown) }
            tile.isEnabled = on != null
        }
        render()
        tile.setOnClickListener {
            val current = toggleState(key) ?: return@setOnClickListener
            applyToggle(key, label, !current)
            // Wi-Fi state settles asynchronously; re-read shortly after as well as now.
            render()
            tile.postDelayed({ render() }, 900)
        }
        return tile
    }

    /**
     * Shared Obsidian sheet: a rounded panel that slides up from the bottom (full width on phones,
     * a centred 600dp card on tablets) with a grab handle, title, optional badge and subtitle.
     */
    private fun sheet(
        pal: Palette,
        m: Metrics,
        title: String,
        badge: String?,
        subtitle: String?,
        build: (LinearLayout, android.app.Dialog) -> Unit,
    ): android.app.Dialog {
        val dialog = android.app.Dialog(this)
        dialog.requestWindowFeature(android.view.Window.FEATURE_NO_TITLE)
        val body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(m.dp(18), m.dp(10), m.dp(18), m.dp(22))
        }
        body.addView(
            View(this).apply {
                background = rounded(pal.line, m.dp(2f))
                layoutParams = LinearLayout.LayoutParams(m.dp(40), m.dp(4)).apply {
                    gravity = Gravity.CENTER_HORIZONTAL
                    bottomMargin = m.dp(14)
                }
            },
        )
        val head = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(m.dp(4), 0, 0, 0)
        }
        head.addView(TextView(this).apply { text = title; style(m.sp(19f), pal.text, 700) })
        if (badge != null) {
            head.addView(
                TextView(this).apply {
                    text = badge
                    style(m.sp(9.5f), pal.c2, 700, mono = true, letterSp = 0.14f)
                    setPadding(m.dp(8), m.dp(3), m.dp(8), m.dp(3))
                    background = rounded(withAlpha(pal.c2, 0.12f), m.dp(6f))
                    layoutParams = LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                    ).apply { leftMargin = m.dp(10) }
                },
            )
        }
        body.addView(head)
        if (subtitle != null) {
            body.addView(
                TextView(this).apply {
                    text = subtitle
                    style(m.sp(12f), pal.muted)
                    setPadding(m.dp(4), m.dp(4), 0, m.dp(14))
                },
            )
        }
        build(body, dialog)
        val r = m.dp(24f)
        val card = FrameLayout(this).apply {
            background = GradientDrawable().apply {
                setColor(pal.surface)
                cornerRadii = if (m.isPhone) floatArrayOf(r, r, r, r, 0f, 0f, 0f, 0f) else FloatArray(8) { r }
                setStroke(m.dp(1), pal.line)
            }
            addView(ScrollView(this@KioskLauncherActivity).apply { addView(body) })
        }
        dialog.setContentView(card)
        dialog.window?.apply {
            setBackgroundDrawable(android.graphics.drawable.ColorDrawable(Color.TRANSPARENT))
            setLayout(m.sheetWidthPx(), ViewGroup.LayoutParams.WRAP_CONTENT)
            setGravity(Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL)
            setDimAmount(if (pal.dark) 0.6f else 0.35f)
            if (!m.isPhone) attributes = attributes.apply { y = m.dp(24) }
        }
        dialog.setOnShowListener {
            if (!animationsOff(this)) {
                card.translationY = card.height.toFloat() + m.dp(40)
                card.animate().translationY(0f).setDuration(340)
                    .setInterpolator(android.view.animation.DecelerateInterpolator(2f)).start()
            }
        }
        dialog.show()
        return dialog
    }

    /** Glass dock pinned to the bottom of the kiosk home: one-tap Rotate / Wi-Fi / Brightness chips
     *  plus the gradient "more" button that opens the full Quick Controls sheet. */
    private fun addDock(pal: Palette, m: Metrics, parent: ViewGroup) {
        dockRefreshers.clear()
        if (!sections().quickControls || !quickControlsAvailable()) return
        val dock = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(m.dp(8), m.dp(8), m.dp(8), m.dp(8))
            background = rounded(pal.glass, m.dp(22f), pal.line, m.dp(1))
            elevation = m.dp(6f)
        }
        val toggles = capabilities.togglePolicies()
        fun chip(key: String, label: String, glyph: String) {
            if (toggles[key] !is ReadableTogglePolicy) return
            val c = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                setPadding(m.dp(10), m.dp(6), m.dp(10), m.dp(6))
                layoutParams = LinearLayout.LayoutParams(0, m.dp(50), 1f).apply { rightMargin = m.dp(6) }
                pressable()
            }
            val g = iconView(iconRes(key), pal.muted, m.dp(20)).apply {
                (layoutParams as LinearLayout.LayoutParams).bottomMargin = m.dp(3)
            }
            val t = TextView(this).apply { text = label; gravity = Gravity.CENTER; style(m.sp(10.5f), pal.muted, 600) }
            c.addView(g); c.addView(t)
            val render = {
                val on = toggleState(key) == true
                c.background = if (on) rounded(withAlpha(pal.c1, 0.16f), m.dp(14f), withAlpha(pal.c1, 0.5f), m.dp(1))
                else rounded(withAlpha(pal.text, 0.04f), m.dp(14f))
                g.setColorFilter(if (on) pal.c1 else pal.muted)
                t.setTextColor(if (on) pal.text else pal.muted)
                t.text = if (key == WifiRadioPolicy.CAPABILITY_KEY && !on && wifiOffAt() > 0) "Wi-Fi off" else label
            }
            render()
            c.setOnClickListener {
                val cur = toggleState(key) ?: return@setOnClickListener
                applyToggle(key, label, !cur)
                render()
                c.postDelayed({ render() }, 900)
            }
            dockRefreshers += render
            dock.addView(c)
        }
        chip(AutoRotationPolicy.CAPABILITY_KEY, "Rotate", "⟳")
        chip(WifiRadioPolicy.CAPABILITY_KEY, "Wi-Fi", "◠")
        capabilities.brightnessLevelPolicy()?.let { b ->
            val c = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                background = rounded(withAlpha(pal.text, 0.04f), m.dp(14f))
                layoutParams = LinearLayout.LayoutParams(0, m.dp(50), 1f).apply { rightMargin = m.dp(6) }
                setOnClickListener { showQuickControlsDialog() }
                pressable()
            }
            val g = iconView(R.drawable.ic_ob_sun, pal.warn, m.dp(20)).apply {
                (layoutParams as LinearLayout.LayoutParams).bottomMargin = m.dp(3)
            }
            val t = TextView(this).apply { gravity = Gravity.CENTER; style(m.sp(10.5f), pal.muted, 600) }
            c.addView(g); c.addView(t)
            val render = { t.text = b.getLevel()?.let { "$it%" } ?: "Brightness" }
            render()
            dockRefreshers += render
            dock.addView(c)
        }
        dock.addView(
            ImageView(this).apply {
                setImageResource(R.drawable.ic_ob_more)
                setColorFilter(Color.WHITE)
                scaleType = ImageView.ScaleType.CENTER_INSIDE
                setPadding(m.dp(13), m.dp(13), m.dp(13), m.dp(13))
                background = gradient(intArrayOf(pal.c1, pal.c2), m.dp(15f))
                layoutParams = LinearLayout.LayoutParams(m.dp(50), m.dp(50))
                contentDescription = "All quick controls"
                setOnClickListener { showQuickControlsDialog() }
                pressable()
            },
        )
        val width = if (m.isPhone) ViewGroup.LayoutParams.MATCH_PARENT else min(resources.displayMetrics.widthPixels - m.dp(32), m.dp(520))
        parent.addView(
            FrameWrap(this, dock, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL, m.dp(12), widthPx = width, avoidSystemBars = true),
        )
        dock.enter(250)
    }

    private fun refreshDock() = dockRefreshers.forEach { it() }

    /** Extend the lock-task allowlist (additive) to include whatever package [intent] actually
     *  resolves to, then start it. No-op (silently) if nothing on-device can handle it. */
    private fun launchAllowlisted(intent: Intent) {
        runCatching {
            val resolved = packageManager.resolveActivity(intent, android.content.pm.PackageManager.MATCH_DEFAULT_ONLY)
            resolved?.activityInfo?.packageName?.let(::ensureAllowlisted)
            startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
    }

    /** "Manage apps" — lets an admin toggle which installed apps show in the kiosk grid, live,
     *  without a console round-trip. Reuses [AppInventoryCollector], the same source the console's
     *  own app picker uses, so the list matches exactly. */
    private fun manageAppsDialog(current: KioskApplyPayload) {
        // Instant path: DeviceOwnerInitializer already warmed this after enrollment, so opening
        // this dialog normally never waits on a live scan. Falls back to scanning live (and
        // populating the cache for next time) for an agent that enrolled before this cache
        // existed, or if warming failed for some reason - a stale cache is never worse than an
        // empty one, but an empty one when a real scan would have worked is a real regression.
        val apps = (AppInventoryCache.get() ?: run { AppInventoryCache.warm(this); AppInventoryCache.get() }
            ?: emptyList()).filterNot { it.pkg == packageName } // we're always allowed; don't show ourselves as a toggle
        if (apps.isEmpty()) {
            toastShort("No launchable apps found")
            return
        }
        val labels = apps.map { it.label }.toTypedArray()
        val checked = apps.map { it.pkg in current.allowedPackages }.toBooleanArray()
        alert()
            .setTitle("Allowed apps")
            .setMultiChoiceItems(labels, checked) { _, which, isChecked -> checked[which] = isChecked }
            .setPositiveButton("Save") { _, _ ->
                val newAllowed = apps.filterIndexed { i, _ -> checked[i] }.map { it.pkg }
                applyAllowedApps(current, newAllowed)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    /** Re-applies kiosk with an updated allowlist: same DPM call [KioskEnterHandler] makes for a
     *  remote kiosk.enter, then persists so [store]'s flow (observed in onCreate) re-renders the
     *  grid — this activity never re-renders itself directly. */
    private fun applyAllowedApps(current: KioskApplyPayload, allowedPackages: List<String>) {
        val updated = current.copy(allowedPackages = allowedPackages)
        val features = lockTaskFeatures(
            KioskToggles(
                home = updated.features.home,
                recents = updated.features.recents,
                notifications = updated.features.notifications,
                systemInfo = updated.features.systemInfo,
                keyguard = updated.features.keyguard,
                lockButtons = updated.features.lockButtons,
            ),
        )
        val allowed = (updated.allowedPackages + listOfNotNull(updated.pinPackage)).distinct()
        when (controller.enter(ComponentName(this, HOME_ALIAS), allowed, features)) {
            KioskResult.Ok -> {
                lifecycleScope.launch { store.save(updated) }
                toastShort("Allowed apps updated")
            }
            else -> toastShort("Failed to update allowed apps")
        }
    }

    private fun ensureAllowlisted(pkg: String) {
        runCatching {
            if (!dpmHandle.dpm.isDeviceOwnerApp(packageName)) return
            if (android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.O) return
            val current = dpmHandle.dpm.getLockTaskPackages(dpmHandle.admin).toList()
            if (pkg !in current) {
                dpmHandle.dpm.setLockTaskPackages(dpmHandle.admin, (current + pkg).distinct().toTypedArray())
            }
        }
    }

    private fun promptResetPasscode() {
        if (android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.O) {
            toastShort("Passcode reset needs Android 8.0 or newer")
            return
        }
        val input = EditText(this).apply {
            inputType = android.text.InputType.TYPE_CLASS_NUMBER or
                android.text.InputType.TYPE_NUMBER_VARIATION_PASSWORD
            hint = "New device PIN (blank clears it)"
        }
        alert()
            .setTitle("Reset device passcode")
            .setMessage("Changes the device's screen-lock PIN directly on this device.")
            .setView(input)
            .setPositiveButton("Set") { _, _ ->
                val token = resetTokenStore.token() ?: resetTokenStore.ensureToken()
                if (token.isEmpty()) {
                    toastShort("No reset token on this device — cannot reset locally")
                    return@setPositiveButton
                }
                val ok = runCatching {
                    dpmHandle.dpm.resetPasswordWithToken(dpmHandle.admin, input.text.toString(), token, 0)
                }.getOrDefault(false)
                toastShort(if (ok) "Passcode updated" else "Reset failed")
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun defaultBrowserPackage(): String? {
        val probe = Intent(Intent.ACTION_VIEW, android.net.Uri.parse("https://"))
        return packageManager.resolveActivity(probe, android.content.pm.PackageManager.MATCH_DEFAULT_ONLY)
            ?.activityInfo?.packageName
    }

    private fun openBrowser() {
        launchAllowlisted(Intent(Intent.ACTION_VIEW, android.net.Uri.parse("https://")))
    }

    private fun openBrowserSettings() {
        val browserPkg = defaultBrowserPackage()
        if (browserPkg == null) {
            toastShort("No browser found on this device")
            return
        }
        launchAllowlisted(
            Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                .setData(android.net.Uri.fromParts("package", browserPkg, null)),
        )
    }

    private fun confirmUninstall() {
        alert()
            .setTitle("Uninstall AMBIC MDM")
            .setMessage(
                "This permanently removes MDM management from this device — it drops Device " +
                    "Owner status and cannot be undone without a factory reset. The console will " +
                    "stop hearing from this device.\n\nAre you sure?",
            )
            .setPositiveButton("Uninstall") { _, _ -> doUninstall() }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun doUninstall() {
        runCatching { events.record("selfUninstall", "admin menu: uninstall initiated on-device") }
        setWatchdogArmed(false)
        KioskEscapeOverlay.hide()
        runCatching { if (isFinishing.not()) stopLockTask() }
        runCatching { controller.exit() }
        runCatching { dpmHandle.dpm.clearDeviceOwnerApp(packageName) }
        runCatching {
            startActivity(
                Intent(Intent.ACTION_DELETE, android.net.Uri.parse("package:$packageName"))
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        }
    }

    private fun showAbout() {
        val versionName = runCatching {
            packageManager.getPackageInfo(packageName, 0).versionName
        }.getOrNull() ?: "unknown"
        alert()
            .setTitle("About AMBIC MDM")
            .setMessage("AMBIC Digital MDM\nVersion $versionName\n\nDevice fleet management agent.")
            .setPositiveButton("OK", null)
            .show()
    }

    private fun toastShort(message: String) {
        android.widget.Toast.makeText(this, message, android.widget.Toast.LENGTH_SHORT).show()
    }

    private fun doExit() {
        // Disarm BEFORE stopLockTask() — see the identical note in bailOnCrashLoop().
        setWatchdogArmed(false)
        // Safety net: clear a stale KioskEscapeOverlay in case exit fires mid-escape — see the
        // identical note in bailOnCrashLoop().
        KioskEscapeOverlay.hide()
        KioskAppKillOverlay.hide()
        runCatching { if (isFinishing.not()) stopLockTask() }
        controller.exit()
        events.record("kioskExit", "exited on-device")
        // Drop the kiosk-only HOME claim and return to AMBIC MDM's status/settings screen
        // (mirrors KioskExitHandler for a remote exit).
        runCatching {
            packageManager.setComponentEnabledSetting(
                ComponentName(this, HOME_ALIAS),
                android.content.pm.PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
                android.content.pm.PackageManager.DONT_KILL_APP,
            )
        }
        lifecycleScope.launch {
            store.save(null)
            runCatching {
                startActivity(Intent(this@KioskLauncherActivity, MainActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
            finish()
        }
    }

    // --- Views -------------------------------------------------------------------------------

    private fun splashView(p: KioskApplyPayload): View {
        resetLiveRefs()
        val bg = parseColor(p.theme.backgroundColor, INK)
        val fg = parseColor(p.theme.textColor, TEXT)
        return frame(bg).apply {
            addView(centeredText("Loading…", 18f, fg))
            addExitAffordance(p, this)
            addStatusBar(p, this)
        }
    }

    /** Palette for the current payload: Obsidian tokens, with the console's kiosk accent colour
     *  (Settings → Kiosk accent) as the secondary accent when one is set. */
    private fun palette(p: KioskApplyPayload?): Palette =
        Palette.of(this, p?.theme?.accentColor?.let { runCatching { Color.parseColor(it) }.getOrNull() })

    /** Drops live-view references before a new screen is built, so the timers never update
     *  views that are no longer on screen. */
    private fun resetLiveRefs() {
        batteryText = null; wifiText = null; clockText = null
        leaderboardBox = null; leaderboardSig = null
        heroTime = null; heroDate = null; batteryRing = null; batteryPct = null
        wifiBarsView = null; wifiName = null
        dockRefreshers.clear()
    }

    /** Kiosk home: status pills, a live hero card (gradient clock, date, device, managed light),
     *  app tiles grouped into showroom apps and tools, and the Quick Controls dock. Every size
     *  comes from [Metrics], so the same code lays out a phone, a tablet or a 12" tablet. */
    private fun launcherGrid(p: KioskApplyPayload): View {
        resetLiveRefs()
        val pal = palette(p)
        val m = Metrics(this)
        val root = FrameLayout(this).apply {
            background = GroundDrawable(pal, m.dp(28f))
            layoutParams = ViewGroup.LayoutParams(MATCH, MATCH)
        }
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        ViewCompat.setOnApplyWindowInsetsListener(column) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            v.setPadding(m.dp(m.gutterDp), bars.top + m.dp(12), m.dp(m.gutterDp), bars.bottom + m.dp(96))
            insets
        }
        val sec = sections()
        // The row always exists (the admin menu button lives in it); the status pills inside it are optional.
        column.addView(topRow(p, pal, m, showPills = sec.statusPills))
        if (sec.clockCard) column.addView(heroCard(p, pal, m))
        if (sec.leaderboard) column.addView(leaderboardCard(pal, m))

        // Group: user-installed apps (Capture, Ornate Buddy, BIS CARE…) are the showroom apps;
        // preloaded system apps (Chrome, Camera, Gallery…) are tools.
        data class Entry(val pkg: String, val label: String, val icon: android.graphics.drawable.Drawable, val system: Boolean)
        val entries = p.allowedPackages.distinct().mapNotNull { pkg ->
            val info = runCatching { packageManager.getApplicationInfo(pkg, 0) }.getOrNull() ?: return@mapNotNull null
            val icon = runCatching { packageManager.getApplicationIcon(pkg) }.getOrNull() ?: return@mapNotNull null
            val label = runCatching { packageManager.getApplicationLabel(info).toString() }.getOrDefault(pkg)
            val system = info.flags and (android.content.pm.ApplicationInfo.FLAG_SYSTEM or
                android.content.pm.ApplicationInfo.FLAG_UPDATED_SYSTEM_APP) != 0
            Entry(pkg, label, icon, system)
        }
        val showroom = entries.filterNot { it.system }
        val tools = entries.filter { it.system }
        var order = 0
        fun section(title: String, list: List<Entry>, featured: Boolean) {
            if (list.isEmpty()) return
            column.addView(sectionLabel(title, pal, m))
            val grid = GridLayout(this).apply {
                columnCount = m.columns()
                layoutParams = LinearLayout.LayoutParams(MATCH, ViewGroup.LayoutParams.WRAP_CONTENT)
            }
            list.forEach { e -> grid.addView(appTile(e.pkg, e.label, e.icon, pal, m, featured, order++)) }
            // Pad the last row with empty cells so tiles keep their column width instead of
            // stretching across the screen when a section has fewer apps than columns.
            repeat((grid.columnCount - list.size % grid.columnCount) % grid.columnCount) {
                grid.addView(
                    android.widget.Space(this),
                    GridLayout.LayoutParams(GridLayout.spec(GridLayout.UNDEFINED, 1f), GridLayout.spec(GridLayout.UNDEFINED, 1f))
                        .apply { width = 0; height = 1 },
                )
            }
            column.addView(grid)
        }
        if (showroom.isNotEmpty() && tools.isNotEmpty()) {
            section("SHOWROOM APPS", showroom, featured = true)
            section("TOOLS", tools, featured = false)
        } else {
            section("APPS", entries.map { it }, featured = false)
        }
        if (entries.isEmpty()) {
            column.addView(
                TextView(this).apply {
                    text = "No available apps. Add installed app packages to this kiosk's allowed list."
                    style(m.sp(14f), pal.muted)
                    setPadding(m.dp(4), m.dp(18), 0, 0)
                },
            )
        }

        // Centre the content column; on wide screens it stops at maxContentDp.
        val holder = FrameLayout(this)
        val contentWidth = if (m.isPhone) MATCH else min(resources.displayMetrics.widthPixels, m.dp(m.maxContentDp))
        holder.addView(column, FrameLayout.LayoutParams(contentWidth, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER_HORIZONTAL))
        root.addView(
            ScrollView(this).apply {
                isFillViewport = true
                isVerticalScrollBarEnabled = false
                addView(holder)
                layoutParams = ViewGroup.LayoutParams(MATCH, MATCH)
            },
        )
        column.requestApplyInsets()
        if (p.exitMode == "gesture") addExitAffordance(p, root)
        addDock(pal, m, root)
        return root
    }

    private val inr: java.text.NumberFormat by lazy {
        java.text.NumberFormat.getInstance(Locale("en", "IN")).apply { maximumFractionDigits = 0 }
    }
    private val timeOnly = SimpleDateFormat("hh:mm a", Locale.ENGLISH)
    private val isoDay = SimpleDateFormat("yyyy-MM-dd", Locale.ENGLISH)

    private fun rupees(v: Double) = "\u20B9" + inr.format(v)

    /** Container for the live sales leaderboard; hidden until the shop has pushed one. */
    private fun leaderboardCard(pal: Palette, m: Metrics): View {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(m.dp(16), m.dp(14), m.dp(16), m.dp(14))
            background = rounded(withAlpha(pal.surface, 0.86f), m.dp(20f), pal.line, m.dp(1))
            layoutParams = LinearLayout.LayoutParams(MATCH, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = m.dp(10) }
            visibility = View.GONE
        }
        leaderboardBox = box
        leaderboardSig = null
        renderLeaderboard()
        return box
    }

    /** Draws the latest cached leaderboard: rank, name, bills, amount, shop total and when it was
     *  last updated ("stale" when the shop server has gone quiet for over 5 minutes). */
    private fun renderLeaderboard() {
        val box = leaderboardBox ?: return
        val lb = LeaderboardRepository.read(this)
        if (lb == null) { box.visibility = View.GONE; leaderboardSig = null; return }
        val now = System.currentTimeMillis()
        val ageMs = (now - lb.receivedAt).coerceAtLeast(0)
        val today = isoDay.format(Date(now))
        val isToday = lb.board.businessDate == today
        val sig = "${lb.hashCode()}|${ageMs / 60_000}|$isToday"
        if (sig == leaderboardSig && box.childCount > 0) return
        val firstDraw = leaderboardSig == null
        leaderboardSig = sig

        val pal = palette(active)
        val m = Metrics(this)
        val maxRows = if (m.isPhone) 5 else 8
        box.removeAllViews()
        box.visibility = View.VISIBLE

        // Header: eyebrow left, freshness right.
        val head = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        head.addView(
            TextView(this).apply {
                text = "TODAY'S SALES"
                style(m.sp(10f), pal.c2, 700, mono = true, letterSp = 0.2f)
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            },
        )
        val stale = ageMs > LEADERBOARD_STALE_MS
        head.addView(
            TextView(this).apply {
                text = if (stale) "Updated ${ageMs / 60_000} min ago" else "Live \u00B7 ${timeOnly.format(Date(lb.receivedAt))}"
                style(m.sp(10.5f), if (stale) pal.warn else pal.ok, 700, mono = true)
            },
        )
        box.addView(head)

        val entries = if (isToday) lb.board.entries.filter { !it.name.equals("none", true) }.take(maxRows) else emptyList()
        if (entries.isEmpty()) {
            box.addView(
                TextView(this).apply {
                    text = "No bills yet today"
                    style(m.sp(14f), pal.muted, 500)
                    setPadding(m.dp(2), m.dp(10), 0, m.dp(4))
                },
            )
            return
        }

        val top = entries.maxOf { it.total }.coerceAtLeast(1.0)
        entries.forEachIndexed { i, e ->
            val medal = when (e.rank) {
                1 -> Color.parseColor("#F5C542")
                2 -> Color.parseColor("#C9D3E0")
                3 -> Color.parseColor("#D9915B")
                else -> null
            }
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(0, m.dp(if (i == 0) 10 else 8), 0, 0)
            }
            val line = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            line.addView(
                TextView(this).apply {
                    text = e.rank.toString()
                    gravity = Gravity.CENTER
                    style(m.sp(12f), if (medal != null) Color.parseColor("#1B1200") else pal.text, 800, mono = true)
                    background = rounded(medal ?: pal.surface2, m.dp(14f), if (medal == null) pal.line else null, m.dp(1))
                    layoutParams = LinearLayout.LayoutParams(m.dp(28), m.dp(28)).apply { rightMargin = m.dp(10) }
                },
            )
            val names = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            }
            names.addView(
                TextView(this).apply {
                    text = e.name
                    style(m.sp(if (e.rank == 1) 16f else 14.5f), pal.text, if (e.rank == 1) 800 else 600)
                    maxLines = 1
                    ellipsize = android.text.TextUtils.TruncateAt.END
                },
            )
            names.addView(
                TextView(this).apply {
                    text = if (e.bills == 1) "1 bill" else "${e.bills} bills"
                    style(m.sp(11.5f), pal.muted)
                },
            )
            line.addView(names)
            line.addView(TextView(this).apply { text = rupees(e.total); style(m.sp(if (e.rank == 1) 17f else 15f), pal.text, 800, mono = true) })
            row.addView(line)
            // Amount relative to the leader, so the gap between people reads at a glance.
            val fill = ((e.total / top) * 1000).toInt().coerceIn(15, 1000)
            val bar = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                layoutParams = LinearLayout.LayoutParams(MATCH, m.dp(4)).apply { topMargin = m.dp(6); leftMargin = m.dp(38) }
            }
            bar.addView(View(this).apply {
                background = gradient(intArrayOf(medal ?: pal.c1, pal.c2), m.dp(2f), GradientDrawable.Orientation.LEFT_RIGHT)
                layoutParams = LinearLayout.LayoutParams(0, MATCH, fill.toFloat())
            })
            if (fill < 1000) bar.addView(View(this).apply { layoutParams = LinearLayout.LayoutParams(0, MATCH, (1000 - fill).toFloat()) })
            row.addView(bar)
            box.addView(row)
            if (firstDraw) row.enter(i * 60L)
        }

        val t = lb.board.totals
        box.addView(
            TextView(this).apply {
                text = "Shop total  ${rupees(t.amount)}  \u00B7  ${t.bills} ${if (t.bills == 1L) "bill" else "bills"}"
                style(m.sp(12f), pal.muted, 600, mono = true)
                setPadding(m.dp(2), m.dp(12), 0, 0)
            },
        )
    }

    /** Battery ring + %, Wi-Fi bars + network name, and the admin menu button when [showAdminMenuButton]. */
    private fun topRow(p: KioskApplyPayload, pal: Palette, m: Metrics, showPills: Boolean = true): View {
        val s = KioskStatusSource.read(this)
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            layoutParams = LinearLayout.LayoutParams(MATCH, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = m.dp(12) }
        }
        fun pill(): LinearLayout = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(m.dp(10), m.dp(7), m.dp(12), m.dp(7))
            background = rounded(pal.glass, m.dp(18f), pal.line, m.dp(1))
        }
        if (showPills) {
            val bat = pill()
            batteryRing = BatteryRingView(this, pal).apply {
                percent = s.batteryPct; charging = s.charging
                layoutParams = LinearLayout.LayoutParams(m.dp(16), m.dp(16)).apply { rightMargin = m.dp(7) }
            }
            batteryPct = TextView(this).apply { style(m.sp(12f), pal.text, 700, mono = true) }
            bat.addView(batteryRing); bat.addView(batteryPct)
            row.addView(bat)

            val wifi = pill().apply {
                layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                    .apply { leftMargin = m.dp(8) }
            }
            wifiBarsView = WifiBarsView(this, pal).apply {
                layoutParams = LinearLayout.LayoutParams(m.dp(16), m.dp(12)).apply { rightMargin = m.dp(7) }
            }
            wifiName = TextView(this).apply {
                style(m.sp(12f), pal.text, 600)
                maxLines = 1
                ellipsize = android.text.TextUtils.TruncateAt.END
                maxWidth = m.dp(if (m.isPhone) 120 else 220)
            }
            wifi.addView(wifiBarsView); wifi.addView(wifiName)
            row.addView(wifi)
        }
        row.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f))

        if (showAdminMenuButton(p)) {
            row.addView(
                ImageView(this).apply {
                    setImageResource(R.drawable.ic_ob_menu)
                    setColorFilter(pal.text)
                    setPadding(m.dp(10), m.dp(10), m.dp(10), m.dp(10))
                    background = rounded(pal.glass, m.dp(12f), pal.line, m.dp(1))
                    contentDescription = "Admin menu"
                    layoutParams = LinearLayout.LayoutParams(m.dp(42), m.dp(42))
                    setOnClickListener { promptExit(p) }
                    pressable()
                },
            )
        }
        updateStatusViews(s)
        return row
    }

    /** Glass hero card: big gradient clock with a blinking colon, full date, device + shop, a
     *  breathing "MANAGED" light and a shimmering accent line along the bottom edge. */
    private fun heroCard(p: KioskApplyPayload, pal: Palette, m: Metrics): View {
        val card = FrameLayout(this).apply {
            background = rounded(withAlpha(pal.surface, 0.86f), m.dp(22f), pal.line, m.dp(1))
            clipToOutline = true
            layoutParams = LinearLayout.LayoutParams(MATCH, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = m.dp(6) }
            enter(0)
        }
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(m.dp(18), m.dp(16), m.dp(18), m.dp(18))
        }
        val clockSp = when { m.isPhone -> 34f; m.isLargeTablet -> 52f; else -> 44f }
        heroTime = TextView(this).apply {
            style(clockSp, pal.c1, 800, mono = true, letterSp = -0.02f)
            // Wrap the text so the gradient spans the digits, not the whole card width.
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            gradientText(pal.c1, pal.c2)
        }
        heroDate = TextView(this).apply {
            style(m.sp(13f), pal.muted, 500)
            setPadding(0, m.dp(4), 0, 0)
        }
        val brand = brand()
        val logoPx = m.dp(when { m.isPhone -> 64; m.isLargeTablet -> 108; else -> 92 })
        val logo = loadBrandBitmap(brand.logo ?: brand.mark, logoPx * 3)
        if (logo != null) {
            // Client brand (e.g. Aradhana Jewellers) sits beside the clock; AMBIC DIGITAL stays in
            // the "powered by" line below as the product brand.
            val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            val left = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            }
            left.addView(heroTime); left.addView(heroDate)
            top.addView(left)
            top.addView(
                ImageView(this).apply {
                    setImageBitmap(logo)
                    adjustViewBounds = true
                    maxHeight = logoPx
                    maxWidth = logoPx * 2
                    contentDescription = brand.name ?: "Client logo"
                    layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                        .apply { leftMargin = m.dp(12) }
                    enter(120)
                },
            )
            col.addView(top)
        } else {
            col.addView(heroTime); col.addView(heroDate)
        }

        val who = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.BOTTOM
            setPadding(0, m.dp(14), 0, 0)
        }
        val names = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        }
        names.addView(
            TextView(this).apply {
                text = p.deviceLabel?.takeIf { it.isNotBlank() } ?: "AMBIC MDM Kiosk"
                style(m.sp(18f), pal.text, 700)
            },
        )
        val org = brand().name ?: p.orgName?.takeIf { it.isNotBlank() }
        names.addView(
            TextView(this).apply {
                text = listOfNotNull(org, "powered by AMBIC DIGITAL").joinToString(" · ")
                style(m.sp(11.5f), pal.muted)
                setPadding(0, m.dp(2), 0, 0)
            },
        )
        who.addView(names)
        val managed = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        managed.addView(
            View(this).apply {
                background = rounded(pal.ok, m.dp(4f))
                layoutParams = LinearLayout.LayoutParams(m.dp(7), m.dp(7)).apply { rightMargin = m.dp(6) }
                breathe(1800)
            },
        )
        managed.addView(TextView(this).apply { text = "MANAGED"; style(m.sp(9.5f), pal.ok, 700, mono = true, letterSp = 0.16f) })
        who.addView(managed)
        col.addView(who)
        card.addView(col)
        card.addView(
            ShimmerLineView(this, pal),
            FrameLayout.LayoutParams(MATCH, m.dp(2), Gravity.BOTTOM),
        )
        renderClock()
        return card
    }

    private fun sectionLabel(title: String, pal: Palette, m: Metrics): TextView = TextView(this).apply {
        text = title
        style(m.sp(10f), pal.c2, 700, mono = true, letterSp = 0.2f)
        setPadding(m.dp(4), m.dp(18), 0, m.dp(4))
    }

    /** One app tile. Showroom apps get a softly breathing accent ring behind the icon. */
    private fun appTile(
        pkg: String,
        label: String,
        icon: android.graphics.drawable.Drawable,
        pal: Palette,
        m: Metrics,
        featured: Boolean,
        index: Int,
    ): View = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER_HORIZONTAL
        setPadding(m.dp(4), m.dp(10), m.dp(4), m.dp(8))
        layoutParams = GridLayout.LayoutParams(
            GridLayout.spec(GridLayout.UNDEFINED, 1f),
            GridLayout.spec(GridLayout.UNDEFINED, 1f),
        ).apply {
            width = 0
            height = ViewGroup.LayoutParams.WRAP_CONTENT
        }
        isClickable = true
        val box = m.dp(m.iconDp + 16)
        val frame = FrameLayout(this@KioskLauncherActivity)
        if (featured) {
            frame.addView(
                View(this@KioskLauncherActivity).apply {
                    background = rounded(withAlpha(pal.c1, 0.08f), m.dp(20f), withAlpha(pal.c1, 0.7f), m.dp(2))
                    breathe(2600, 0.25f)
                },
                FrameLayout.LayoutParams(box, box),
            )
        } else {
            frame.addView(
                View(this@KioskLauncherActivity).apply { background = rounded(withAlpha(pal.surface, 0.7f), m.dp(20f), pal.line, m.dp(1)) },
                FrameLayout.LayoutParams(box, box),
            )
        }
        frame.addView(
            ImageView(this@KioskLauncherActivity).apply { setImageDrawable(icon) },
            FrameLayout.LayoutParams(m.dp(m.iconDp), m.dp(m.iconDp), Gravity.CENTER),
        )
        addView(frame, LinearLayout.LayoutParams(box, box))
        addView(
            TextView(this@KioskLauncherActivity).apply {
                text = label
                style(m.sp(12.5f), pal.text, 500)
                gravity = Gravity.CENTER
                maxLines = 2
                ellipsize = android.text.TextUtils.TruncateAt.END
                setPadding(0, m.dp(7), 0, 0)
            },
        )
        pressable()
        enter(80L + index * 45L)
        setOnClickListener {
            runCatching {
                packageManager.getLaunchIntentForPackage(pkg)?.let { startActivity(it) }
            }
            // Grid mode (the actual production configuration -- explicit correction,
            // 2026-09-20: no tablet ever runs single-pin mode) needs the kill switch retargeted
            // to whichever app was just opened, not fixed to one pinned package. See
            // KioskAppKillOverlay.show()'s doc comment for the retarget behavior.
            KioskAppKillOverlay.show(this@KioskLauncherActivity) { killAndRelaunchPinnedApp(pkg) }
        }
    }

    private fun idleView(): View {
        resetLiveRefs()
        val pal = palette(null)
        val m = Metrics(this)
        return FrameLayout(this).apply {
            background = GroundDrawable(pal, m.dp(28f))
            layoutParams = ViewGroup.LayoutParams(MATCH, MATCH)
            val col = LinearLayout(this@KioskLauncherActivity).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                layoutParams = ViewGroup.LayoutParams(MATCH, MATCH)
            }
            val brand = brand()
            val logoW = kotlin.math.min(resources.displayMetrics.widthPixels * 6 / 10, m.dp(380))
            val logo = loadBrandBitmap(brand.logo ?: brand.mark, logoW)
            if (logo != null) {
                col.addView(
                    ImageView(this@KioskLauncherActivity).apply {
                        setImageBitmap(logo)
                        adjustViewBounds = true
                        maxWidth = logoW
                        maxHeight = logoW
                        contentDescription = brand.name ?: "Client logo"
                        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                            .apply { bottomMargin = m.dp(28) }
                    },
                )
            } else {
                col.addView(
                    TextView(this@KioskLauncherActivity).apply {
                        text = "MDM"
                        gravity = Gravity.CENTER
                        style(m.sp(14f), Color.WHITE, 800, mono = true)
                        background = gradient(intArrayOf(pal.c1, pal.c2, pal.c3), m.dp(18f))
                        layoutParams = LinearLayout.LayoutParams(m.dp(64), m.dp(64)).apply { bottomMargin = m.dp(16) }
                    },
                )
            }
            col.addView(
                TextView(this@KioskLauncherActivity).apply {
                    text = "AMBIC MDM"
                    gravity = Gravity.CENTER
                    style(m.sp(28f), pal.c1, 800)
                    gradientText(pal.c1, pal.c2)
                },
            )
            col.addView(
                TextView(this@KioskLauncherActivity).apply {
                    text = if (brand.name != null) "Managed device · ${brand.name}" else "Managed device"
                    gravity = Gravity.CENTER
                    style(m.sp(14f), pal.muted)
                    setPadding(0, m.dp(6), 0, 0)
                },
            )
            col.enter(0)
            addView(col)
            addQuickControlsAffordance(this)
        }
    }

    private fun recoveryView(): View {
        resetLiveRefs()
        val pal = palette(null)
        val m = Metrics(this)
        return FrameLayout(this).apply {
            background = GroundDrawable(pal, m.dp(28f))
            layoutParams = ViewGroup.LayoutParams(MATCH, MATCH)
            val col = LinearLayout(this@KioskLauncherActivity).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                setPadding(m.dp(28), 0, m.dp(28), 0)
                layoutParams = ViewGroup.LayoutParams(MATCH, MATCH)
            }
            col.addView(TextView(this@KioskLauncherActivity).apply {
                text = "Kiosk stopped"; gravity = Gravity.CENTER; style(m.sp(22f), pal.alert, 700)
            })
            col.addView(TextView(this@KioskLauncherActivity).apply {
                text = "A kiosk app crashed repeatedly, so kiosk mode was disabled to keep the device usable."
                gravity = Gravity.CENTER
                style(m.sp(14f), pal.muted)
                setPadding(0, m.dp(12), 0, 0)
            })
            addView(col)
        }
    }

    /** Pushes one [KioskStatusSource] read into whichever status views are on screen. */
    private fun updateStatusViews(s: KioskStatusSource.Status) {
        batteryText?.text = formatBattery(s)
        wifiText?.text = formatWifi(s)
        batteryRing?.let { it.percent = s.batteryPct; it.charging = s.charging }
        batteryPct?.text = if (s.batteryPct >= 0) "${s.batteryPct}%${if (s.charging) " ⚡" else ""}" else "—"
        wifiBarsView?.let { it.connected = s.wifiConnected; it.bars = if (s.wifiConnected) s.wifiBars.coerceIn(1, 4) else 0 }
        wifiName?.text = when {
            !s.wifiConnected -> "Wi-Fi off"
            s.ssid != null -> s.ssid
            else -> "Wi-Fi"
        }
        refreshDock()
    }

    /** Clock text for both the legacy status bar (splash) and the hero card. The hero colon
     *  blinks once a second (hidden on odd seconds) unless animations are off. */
    private fun renderClock() {
        val now = Date()
        clockText?.text = clockFormat.format(now)
        heroTime?.let { tv ->
            val hm = heroTimeFormat.format(now)
            val ampm = " " + heroAmPmFormat.format(now)
            val span = android.text.SpannableString(hm + ampm)
            val blinkOff = (System.currentTimeMillis() / 1000) % 2 == 1L && !animationsOff(this)
            if (blinkOff) {
                span.setSpan(android.text.style.ForegroundColorSpan(Color.TRANSPARENT), 2, 3, android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            }
            span.setSpan(android.text.style.RelativeSizeSpan(0.42f), hm.length, span.length, android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            tv.text = span
        }
        heroDate?.text = heroDateFormat.format(now)
    }

    /** Add the per-[KioskApplyPayload.exitMode] exit affordance to [parent]. */
    private fun addExitAffordance(p: KioskApplyPayload, parent: ViewGroup) {
        when (p.exitMode) {
            "visible" -> {
                // A standard kebab (⋮) icon rather than a text button — this is the one entry
                // point to the whole admin menu (exit is now just one item in it, not the only
                // outcome), so it should read as "menu," not "exit."
                val kebab = TextView(this).apply {
                    text = "⋮"
                    setTextColor(parseColor(p.theme.accentColor, TEXT))
                    textSize = 22f
                    gravity = Gravity.CENTER
                    setBackgroundColor(Color.argb(90, 0, 0, 0))
                    setOnClickListener { promptExit(p) }
                }
                parent.addView(
                    FrameWrap(this, kebab, Gravity.TOP or Gravity.END, dp(16), dp(48), dp(48), avoidSystemBars = true),
                )
            }
            "gesture" -> {
                // Invisible top-right corner target; 7 taps within the window opens the prompt.
                val target = View(this).apply {
                    var taps = 0
                    var first = 0L
                    setOnClickListener {
                        val nowMs = System.currentTimeMillis()
                        if (nowMs - first > GESTURE_WINDOW_MS) { taps = 0; first = nowMs }
                        if (++taps >= GESTURE_TAPS) { taps = 0; promptExit(p) }
                    }
                }
                parent.addView(
                    FrameWrap(this, target, Gravity.TOP or Gravity.END, 0, dp(72), dp(72), avoidSystemBars = true),
                )
            }
            else -> Unit // "remote": no on-device exit
        }
    }

    /** Battery (extreme left) and Wi-Fi (extreme right) readouts, both flush with the true top
     *  edge — same row as the exit affordance, not stacked under it. Re-points [batteryText]/
     *  [wifiText] so the shared poll loop ([statusTick]) keeps whichever copies are on screen
     *  live across [setContentView] swaps. Coloured by [KioskThemeDto.accentColor] when set.
     *  Wi-Fi is offset left of the kebab menu when [KioskApplyPayload.exitMode] is "visible" so
     *  the two top-end elements sit side by side instead of overlapping; the "gesture" tap target
     *  is invisible, so no offset needed. */
    private fun addStatusBar(p: KioskApplyPayload, parent: ViewGroup) {
        val color = parseColor(p.theme.accentColor, parseColor(p.theme.textColor, TEXT))
        val s = KioskStatusSource.read(this@KioskLauncherActivity)

        // All three status items share one 32dp row and are vertically centered in it, so the
        // larger clock text lines up with battery/Wi-Fi instead of sitting lower than them.
        val battery = text("", 12f, color).apply { text = formatBattery(s); gravity = Gravity.CENTER_VERTICAL }
        batteryText = battery
        parent.addView(
            FrameWrap(this, battery, Gravity.TOP or Gravity.START, dp(16), heightPx = dp(32), avoidSystemBars = true),
        )

        val wifi = text("", 12f, color).apply { text = formatWifi(s); gravity = Gravity.CENTER_VERTICAL }
        wifiText = wifi
        val endExtra = if (showAdminMenuButton(p)) dp(52) else 0
        parent.addView(
            FrameWrap(
                this, wifi, Gravity.TOP or Gravity.END, dp(16),
                heightPx = dp(32), endExtraPx = endExtra, avoidSystemBars = true,
            ),
        )

        // Date/time, top-center on the same row. Width is fitted after layout to the gap between
        // battery and Wi-Fi (see fitClock) and the text auto-shrinks 16sp -> 10sp to fit, so it
        // never overlaps them on a narrow phone; FrameWrap already pushes it below the status bar
        // and any top display cutout.
        val clock = TextView(this).apply {
            setTextColor(color)
            setTypeface(typeface, Typeface.BOLD)
            gravity = Gravity.CENTER
            maxLines = 1
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            text = clockFormat.format(Date())
        }
        clockText = clock
        parent.addView(
            FrameWrap(
                this, clock, Gravity.TOP or Gravity.CENTER_HORIZONTAL, dp(16),
                widthPx = dp(220), heightPx = dp(32), avoidSystemBars = true,
            ),
        )
        TextViewCompat.setAutoSizeTextTypeUniformWithConfiguration(clock, 10, 16, 1, TypedValue.COMPLEX_UNIT_SP)
        val refit = View.OnLayoutChangeListener { _, _, _, _, _, _, _, _, _ -> clock.post { fitClock() } }
        battery.addOnLayoutChangeListener(refit)
        wifi.addOnLayoutChangeListener(refit)
        parent.addOnLayoutChangeListener(refit)
    }

    /** Sizes [clockText] to the widest centered band that clears both [batteryText] (left) and
     *  [wifiText] (right, already offset past the kebab menu), minus a small gap each side. */
    private fun fitClock() {
        val clock = clockText ?: return
        val battery = batteryText ?: return
        val wifi = wifiText ?: return
        if (clock.width == 0 && battery.width == 0) return
        val loc = IntArray(2)
        battery.getLocationInWindow(loc)
        val leftEdge = loc[0] + battery.width
        wifi.getLocationInWindow(loc)
        val rightEdge = loc[0]
        val center = window.decorView.width / 2
        val half = minOf(center - leftEdge, rightEdge - center) - dp(12)
        val target = (2 * half).coerceIn(dp(60), dp(320))
        val lp = clock.layoutParams ?: return
        if (lp.width != target) {
            lp.width = target
            clock.layoutParams = lp
        }
    }

    private fun formatBattery(s: KioskStatusSource.Status): String =
        if (s.batteryPct >= 0) "🔋 ${s.batteryPct}%${if (s.charging) " ⚡" else ""}" else "🔋 —"

    private fun formatWifi(s: KioskStatusSource.Status): String {
        val bars = s.wifiBars.coerceIn(0, 4)
        return if (!s.wifiConnected) "Wi-Fi off" else "Wi-Fi " + "●".repeat(bars + 1) + "○".repeat(4 - bars)
    }

    // --- View helpers ------------------------------------------------------------------------

    private fun frame(bg: Int): android.widget.FrameLayout =
        android.widget.FrameLayout(this).apply {
            setBackgroundColor(bg)
            layoutParams = ViewGroup.LayoutParams(MATCH, MATCH)
        }

    private fun centeredText(s: String, sizeSp: Float, color: Int, bold: Boolean = false): TextView =
        text(s, sizeSp, color, bold).apply { gravity = Gravity.CENTER }

    private fun text(s: String, sizeSp: Float, color: Int, bold: Boolean = false): TextView =
        TextView(this).apply {
            text = s
            setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp)
            setTextColor(color)
            if (bold) setTypeface(typeface, Typeface.BOLD)
        }

    private fun iconCellPx(size: String?): Int = when (size?.uppercase()) {
        "LARGE" -> dp(96)
        "MEDIUM" -> dp(72)
        else -> dp(56)
    }

    private fun parseColor(value: String?, fallback: Int): Int =
        value?.let { runCatching { Color.parseColor(it) }.getOrNull() } ?: fallback

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    private fun defaultKioskPayload(): KioskApplyPayload =
        KioskApplyPayload(
            mode = "launcher",
            allowedPackages = listOf(
                "com.ornate.nx",
                "com.bis.bisapp",
                "com.android.chrome",
                "com.android.camera",
                "com.miui.gallery",
                "com.google.android.apps.photos",
                "com.miui.calculator",
                "com.android.contacts",
            ),
            exitMode = "visible",
            password = "admin",
            features = com.mdmesh.proto.KioskFeaturesDto(
                home = true,
                recents = true,
                notifications = false,
                systemInfo = true,
                keyguard = false,
                lockButtons = true,
            ),
            deviceLabel = "AMBIC MDM Kiosk",
            orgName = "Aradhana Jewellers",
        )

    private companion object {
        const val MATCH = ViewGroup.LayoutParams.MATCH_PARENT
        const val GESTURE_TAPS = 7
        const val GESTURE_WINDOW_MS = 3_000L
        const val STATUS_POLL_MS = 15_000L
        const val LEADERBOARD_POLL_MS = 30_000L
        const val LEADERBOARD_STALE_MS = 5 * 60_000L
        const val PREF_WIFI_OFF_AT = "wifiOffAt"
        const val HOME_ALIAS = "com.mdmesh.agent.KioskHomeAlias"
        val INK = Color.parseColor("#0E1117")
        val TEXT = Color.parseColor("#E8EEF4")
        val MUTED = Color.parseColor("#8693A4")
        // TEXT/MUTED are tuned for content drawn over the app's own dark (INK) screens.
        // Any custom view placed inside a plain system AlertDialog (white background) needs a
        // dark color instead, or it renders as near-invisible pale text on white — this is what
        // showQuickControlsDialog's row labels used to do before this constant existed.
        val DIALOG_TEXT = Color.parseColor("#1B2733")
        val SIGNAL = Color.parseColor("#F4B942")
        val ALERT = Color.parseColor("#F2545B")
    }
}

/** A [android.widget.FrameLayout.LayoutParams]-positioned wrapper, kept tiny for the launcher's
 *  programmatic UI (no XML). Places [child] at [gravity] with optional margins/size. */
private class FrameWrap(
    activity: ComponentActivity,
    child: View,
    gravity: Int,
    marginPx: Int,
    widthPx: Int = ViewGroup.LayoutParams.WRAP_CONTENT,
    heightPx: Int = ViewGroup.LayoutParams.WRAP_CONTENT,
    /** Extra offset added only on the edge(s) [gravity] touches — e.g. pushing a second TOP|END
     *  element down below a sibling (like the kebab menu) that already occupies that corner. */
    topExtraPx: Int = 0,
    /** Extra offset on the END/right edge — for placing a second TOP|END element *beside* a
     *  sibling (like the kebab menu) on the same row instead of stacking it underneath. */
    endExtraPx: Int = 0,
    /** Whether to push the child out from under the system bars on the edge(s) [gravity] touches.
     *  Kiosk mode hides the system bars, so text-only readouts (like the status line) can hug the
     *  true screen edge instead; leave true for real tap targets (kebab menu, gesture corner) in
     *  case the bars are ever visible. */
    avoidSystemBars: Boolean = true,
) : android.widget.FrameLayout(activity) {
    init {
        layoutParams = ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT,
        )
        addView(
            child,
            android.widget.FrameLayout.LayoutParams(widthPx, heightPx, gravity).apply {
                setMargins(marginPx, marginPx + topExtraPx, marginPx + endExtraPx, marginPx)
            },
        )
        // Android 15 (targetSdk 35) draws edge-to-edge by default, so the nav/status bars overlay
        // content instead of reserving their own space — without this, a bottom- or top-gravity
        // exit affordance sits partially behind the system bar. Push the child out from under
        // whichever system bar edges its gravity touches.
        ViewCompat.setOnApplyWindowInsetsListener(this) { _, insets ->
            val bars = if (avoidSystemBars) {
                insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            } else Insets.NONE
            val lp = child.layoutParams as android.widget.FrameLayout.LayoutParams
            lp.bottomMargin = marginPx + if (gravity and Gravity.BOTTOM == Gravity.BOTTOM) bars.bottom else 0
            lp.topMargin = marginPx + topExtraPx + if (gravity and Gravity.TOP == Gravity.TOP) bars.top else 0
            lp.leftMargin = marginPx + if (gravity and Gravity.START == Gravity.START || gravity and Gravity.LEFT == Gravity.LEFT) bars.left else 0
            lp.rightMargin = marginPx + endExtraPx + if (gravity and Gravity.END == Gravity.END || gravity and Gravity.RIGHT == Gravity.RIGHT) bars.right else 0
            child.layoutParams = lp
            insets
        }
        requestApplyInsets()
    }
}
