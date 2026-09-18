package com.mdmesh.agent

import android.app.ActivityManager
import android.content.ComponentName
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.GridLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.appcompat.app.AlertDialog
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.fragment.app.FragmentActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.flow.distinctUntilChanged
import com.mdmesh.agent.service.CheckInService
import com.mdmesh.core.action.ResetPasswordTokenStore
import com.mdmesh.core.device.AppInventoryCache
import com.mdmesh.core.device.AppInventoryCollector
import com.mdmesh.core.store.AdminPasscodeStore
import com.mdmesh.core.store.KioskStateStore
import com.mdmesh.core.telemetry.EventSink
import com.mdmesh.kiosk.CrashLoopGuard
import com.mdmesh.kiosk.KioskController
import com.mdmesh.kiosk.KioskEscapeOverlay
import com.mdmesh.kiosk.KioskResult
import com.mdmesh.kiosk.KioskToggles
import com.mdmesh.kiosk.lockTaskFeatures
import com.mdmesh.policy.wifi.DpmHandle
import com.mdmesh.proto.KioskApplyPayload
import com.mdmesh.proto.PasscodeHash
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject

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

    /** Last applied non-null kiosk state, so [onResume] can recover a bounced single-app pin. */
    private var active: KioskApplyPayload? = null

    /** Cached mirror of [AdminPasscodeStore], kept current so [promptExit] can check it
     *  synchronously without blocking on a DataStore read from a dialog callback. */
    private var fleetPasscodeHash: String? = null

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
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                adminPasscodeStore.flow().distinctUntilChanged().collect { fleetPasscodeHash = it }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // A single-app pin that returned us to HOME means the pinned app exited or crashed — re-pin
        // it (counting the bounce so a crash loop trips the guard). Enter/exit transitions are
        // handled by the flow collector, not here.
        val p = active ?: return
        if (p.mode == "single") {
            crashGuard.registerFault()
            if (bailOnCrashLoop()) return
            launchPinned(p)
        }
    }

    private fun applyState(p: KioskApplyPayload?) {
        active = p
        setWatchdogArmed(p != null)
        if (p == null) {
            stopLockTaskSafely()
            setContentView(idleView())
            return
        }
        if (bailOnCrashLoop()) return
        promptDefaultHomeIfNeeded()
        startLockTaskSafely()
        if (p.mode == "single" && p.pinPackage != null) {
            launchPinned(p)
        } else {
            setContentView(launcherGrid(p))
        }
    }

    /** Launch + show the pinned app (single mode), with a themed splash behind it. */
    private fun launchPinned(p: KioskApplyPayload) {
        val intent = p.pinPackage?.let { packageManager.getLaunchIntentForPackage(it) }
        if (intent == null) {
            setContentView(launcherGrid(p)) // unknown package → fall back to the grid
            return
        }
        setContentView(splashView(p))
        runCatching { startActivity(intent) }
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
        AlertDialog.Builder(this)
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
        val input = EditText(this).apply {
            inputType = android.text.InputType.TYPE_CLASS_TEXT or
                android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
            hint = "Admin password"
        }
        AlertDialog.Builder(this)
            .setTitle("Admin access")
            .setView(input)
            .setPositiveButton("Continue") { _, _ ->
                val entered = input.text.toString()
                // Either the per-session password or the fleet-wide admin passcode (set from the
                // web console's Settings page, delivered on check-in) unlocks the admin menu.
                val sessionMatch = pw != null && entered == pw
                val fleetMatch = !fleetHash.isNullOrBlank() && PasscodeHash.matches(entered, fleetHash)
                if (sessionMatch || fleetMatch) showAdminMenu(p)
            }
            .setNegativeButton("Cancel", null)
            .show()
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

    private fun showAdminMenu(p: KioskApplyPayload) {
        val items = arrayOf(
            "Reset passcode",
            "Manage apps",
            "Set default application",
            "Change background",
            "Browser shortcuts",
            "Browser settings",
            "Configure Wi-Fi",
            "Open system settings",
            "Uninstall AMBIC MDM",
            "About AMBIC MDM",
            "Exit AMBIC MDM",
        )
        AlertDialog.Builder(this)
            .setTitle("Admin menu")
            .setItems(items) { _, which ->
                when (which) {
                    0 -> promptResetPasscode()
                    1 -> manageAppsDialog(p)
                    2 -> launchAllowlisted(Intent(android.provider.Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS))
                    3 -> launchAllowlisted(Intent(Intent.ACTION_SET_WALLPAPER))
                    4 -> openBrowser()
                    5 -> openBrowserSettings()
                    6 -> launchAllowlisted(Intent(android.provider.Settings.ACTION_WIFI_SETTINGS))
                    7 -> launchAllowlisted(Intent(android.provider.Settings.ACTION_SETTINGS))
                    8 -> confirmUninstall()
                    9 -> showAbout()
                    10 -> doExit()
                }
            }
            .setNegativeButton("Close", null)
            .show()
    }

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
        AlertDialog.Builder(this)
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
        AlertDialog.Builder(this)
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
        AlertDialog.Builder(this)
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
        AlertDialog.Builder(this)
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
        val bg = parseColor(p.theme.backgroundColor, INK)
        val fg = parseColor(p.theme.textColor, TEXT)
        return frame(bg).apply {
            addView(centeredText("Loading…", 18f, fg))
            addExitAffordance(p, this)
        }
    }

    private fun launcherGrid(p: KioskApplyPayload): View {
        val bg = parseColor(p.theme.backgroundColor, INK)
        val fg = parseColor(p.theme.textColor, TEXT)
        val cell = iconCellPx(p.theme.iconSize)
        val cols = maxOf(2, (resources.displayMetrics.widthPixels - dp(24)) / (cell + dp(24)))

        val grid = GridLayout(this).apply {
            columnCount = cols
            setPadding(dp(12), dp(16), dp(12), dp(28))
        }
        var rendered = 0
        for (pkg in p.allowedPackages.distinct()) {
            val app = runCatching { packageManager.getApplicationInfo(pkg, 0) }.getOrNull() ?: continue
            val icon = runCatching { packageManager.getApplicationIcon(pkg) }.getOrNull() ?: continue
            val label = runCatching { packageManager.getApplicationLabel(app).toString() }.getOrDefault(pkg)
            grid.addView(appCell(pkg, label, icon, cell, fg))
            rendered++
        }

        // Always render a header + (when nothing resolved) an empty-state, so kiosk is never a
        // bare black screen — that previously happened whenever the allowlist was empty or none of
        // the packages were installed on the device.
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(28), dp(24), dp(12))
            layoutParams = ViewGroup.LayoutParams(MATCH, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
        column.addView(text(p.deviceLabel?.takeIf { it.isNotBlank() } ?: "AMBIC MDM Kiosk", 20f, fg, bold = true))
        p.orgName?.takeIf { it.isNotBlank() }?.let { column.addView(text(it, 14f, fg)) }
        column.addView(
            text("powered by AMBIC DIGITAL", 10f, MUTED).apply { setPadding(0, dp(2), 0, 0) },
        )
        if (rendered == 0) {
            column.addView(
                text(
                    "No available apps. Add installed app packages to this kiosk's allowed list.",
                    14f,
                    MUTED,
                ).apply { setPadding(0, dp(10), 0, 0) },
            )
        }
        column.addView(grid)

        val root = frame(bg)
        root.addView(
            ScrollView(this).apply {
                addView(column)
                layoutParams = ViewGroup.LayoutParams(MATCH, MATCH)
            },
        )
        addExitAffordance(p, root)
        return root
    }

    private fun appCell(
        pkg: String,
        label: String,
        icon: android.graphics.drawable.Drawable,
        cellPx: Int,
        fg: Int,
    ): View = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER
        setPadding(dp(12), dp(12), dp(12), dp(12))
        isClickable = true
        addView(
            ImageView(this@KioskLauncherActivity).apply {
                setImageDrawable(icon)
                layoutParams = LinearLayout.LayoutParams(cellPx, cellPx)
            },
        )
        addView(
            text(label, 12f, fg).apply {
                gravity = Gravity.CENTER
                maxLines = 1
                setPadding(0, dp(6), 0, 0)
            },
        )
        setOnClickListener {
            runCatching {
                packageManager.getLaunchIntentForPackage(pkg)?.let { startActivity(it) }
            }
        }
    }

    private fun idleView(): View = frame(INK).apply {
        val col = LinearLayout(this@KioskLauncherActivity).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            layoutParams = ViewGroup.LayoutParams(MATCH, MATCH)
        }
        col.addView(centeredText("AMBIC MDM", 28f, SIGNAL, bold = true))
        col.addView(centeredText("Managed device", 14f, MUTED))
        addView(col)
    }

    private fun recoveryView(): View = frame(INK).apply {
        val col = LinearLayout(this@KioskLauncherActivity).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(28), 0, dp(28), 0)
            layoutParams = ViewGroup.LayoutParams(MATCH, MATCH)
        }
        col.addView(centeredText("Kiosk stopped", 22f, ALERT, bold = true))
        col.addView(
            centeredText(
                "A kiosk app crashed repeatedly, so kiosk mode was disabled to keep the device usable.",
                14f,
                MUTED,
            ).apply { setPadding(0, dp(12), 0, 0) },
        )
        addView(col)
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
                    setTextColor(TEXT)
                    textSize = 22f
                    gravity = Gravity.CENTER
                    setBackgroundColor(Color.argb(90, 0, 0, 0))
                    setOnClickListener { promptExit(p) }
                }
                parent.addView(
                    FrameWrap(this, kebab, Gravity.TOP or Gravity.END, dp(16), dp(48), dp(48)),
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
                    FrameWrap(this, target, Gravity.TOP or Gravity.END, 0, dp(72), dp(72)),
                )
            }
            else -> Unit // "remote": no on-device exit
        }
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

    private companion object {
        const val MATCH = ViewGroup.LayoutParams.MATCH_PARENT
        const val GESTURE_TAPS = 7
        const val GESTURE_WINDOW_MS = 3_000L
        const val HOME_ALIAS = "com.mdmesh.agent.KioskHomeAlias"
        val INK = Color.parseColor("#0E1117")
        val TEXT = Color.parseColor("#E8EEF4")
        val MUTED = Color.parseColor("#8693A4")
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
) : android.widget.FrameLayout(activity) {
    init {
        layoutParams = ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT,
        )
        addView(
            child,
            android.widget.FrameLayout.LayoutParams(widthPx, heightPx, gravity).apply {
                setMargins(marginPx, marginPx, marginPx, marginPx)
            },
        )
        // Android 15 (targetSdk 35) draws edge-to-edge by default, so the nav/status bars overlay
        // content instead of reserving their own space — without this, a bottom- or top-gravity
        // exit affordance sits partially behind the system bar. Push the child out from under
        // whichever system bar edges its gravity touches.
        ViewCompat.setOnApplyWindowInsetsListener(this) { _, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            val lp = child.layoutParams as android.widget.FrameLayout.LayoutParams
            lp.bottomMargin = marginPx + if (gravity and Gravity.BOTTOM == Gravity.BOTTOM) bars.bottom else 0
            lp.topMargin = marginPx + if (gravity and Gravity.TOP == Gravity.TOP) bars.top else 0
            lp.leftMargin = marginPx + if (gravity and Gravity.START == Gravity.START || gravity and Gravity.LEFT == Gravity.LEFT) bars.left else 0
            lp.rightMargin = marginPx + if (gravity and Gravity.END == Gravity.END || gravity and Gravity.RIGHT == Gravity.RIGHT) bars.right else 0
            child.layoutParams = lp
            insets
        }
        requestApplyInsets()
    }
}
