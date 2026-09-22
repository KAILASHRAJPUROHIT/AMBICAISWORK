package com.mdmesh.agent.service

import android.app.ActivityOptions
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.util.Log
import androidx.core.content.ContextCompat
import com.mdmesh.agent.KioskLauncherActivity
import com.mdmesh.core.store.KioskStateStore
import com.mdmesh.core.sync.CheckInWorker
import com.mdmesh.core.telemetry.EventLog
import com.mdmesh.kiosk.KioskController
import com.mdmesh.kiosk.KioskToggles
import com.mdmesh.kiosk.lockTaskFeatures
import com.mdmesh.policy.wifi.DpmHandle
import com.mdmesh.proto.EventType
import com.mdmesh.proto.KioskApplyPayload
import com.mdmesh.proto.KioskFeaturesDto
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Restarts the wake-to-sync foreground service after a reboot or a self-update, so a parked device
 * re-establishes its channel without anyone opening the app. WorkManager reschedules its own 15-min
 * floor across reboots; this restores the instant channel sooner.
 *
 * Also restores the MDM Kiosk mode immediately post-update and post-boot so managed devices do not
 * drop to the OEM launcher.
 */
@AndroidEntryPoint
class BootReceiver : BroadcastReceiver() {

    @Inject lateinit var kioskStateStore: KioskStateStore
    @Inject lateinit var kioskController: KioskController
    @Inject lateinit var dpmHandle: DpmHandle

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            runCatching { EventLog(context).record(EventType.BOOT) }
        }
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED -> {
                // Enqueue a check-in via WorkManager FIRST: this reliably runs from the background
                // (including right after a self-update), so connectivity resumes in seconds even
                // when starting the foreground service from a background receiver is blocked on
                // Android 12+. The FGS start below is best-effort (restores the instant socket when
                // the OS allows it from this broadcast).
                runCatching { CheckInWorker.scheduleNow(context) }
                // The service starts as specialUse on API 34+ (see the manifest note), which —
                // unlike dataSync — Android 15 permits from BOOT_COMPLETED. runCatching stays as
                // the belt-and-braces: if an OEM still refuses, the worker above covers.
                runCatching {
                    ContextCompat.startForegroundService(
                        context,
                        Intent(context, CheckInService::class.java),
                    )
                }
                // Re-arm the doze-proof heartbeat (AlarmManager alarms don't survive reboot).
                runCatching { WakeKeepAlive.schedule(context) }

                // Restore kiosk mode and bring KioskLauncherActivity to foreground.
                val pending = goAsync()
                CoroutineScope(Dispatchers.Main).launch {
                    try {
                        restoreKioskIfNeeded(context)
                    } catch (t: Throwable) {
                        Log.e(TAG, "Failed to restore kiosk on boot/update", t)
                    } finally {
                        pending.finish()
                    }
                }
            }
        }
    }

    private suspend fun restoreKioskIfNeeded(context: Context) {
        val isDo = runCatching { dpmHandle.dpm.isDeviceOwnerApp(context.packageName) }.getOrDefault(false)
        val lastKnown = kioskStateStore.loadLastKnown()

        // Device Owner devices ALWAYS enter kiosk mode by default post-update/reboot.
        // Non-DO devices only enter if a kiosk payload was previously applied.
        if (!isDo && lastKnown == null) return

        val payload = lastKnown ?: defaultKioskPayload()

        // Save active state so observers see it
        kioskStateStore.save(payload)

        val homeAlias = ComponentName(context, "com.mdmesh.agent.KioskHomeAlias")

        // 1. Enable KioskHomeAlias
        runCatching {
            context.packageManager.setComponentEnabledSetting(
                homeAlias,
                PackageManager.COMPONENT_ENABLED_STATE_ENABLED,
                PackageManager.DONT_KILL_APP,
            )
        }

        // Clear any previous IME restriction — allow all system keyboards (Gboard, etc.)
        if (isDo) {
            runCatching {
                dpmHandle.dpm.setPermittedInputMethods(dpmHandle.admin, null)
            }
        }

        // 2. Apply lock task settings
        val features = lockTaskFeatures(
            KioskToggles(
                home = payload.features.home,
                recents = payload.features.recents,
                notifications = payload.features.notifications,
                systemInfo = payload.features.systemInfo,
                keyguard = payload.features.keyguard,
                lockButtons = payload.features.lockButtons,
            ),
        )
        val allowed = (payload.allowedPackages + listOfNotNull(payload.pinPackage)).distinct()
        runCatching {
            kioskController.enter(homeAlias, allowed, features)
        }

        // 3. Bring KioskLauncherActivity to the foreground
        runCatching {
            val kioskIntent = Intent(context, KioskLauncherActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                val options = ActivityOptions.makeBasic().apply {
                    pendingIntentBackgroundActivityStartMode = ActivityOptions.MODE_BACKGROUND_ACTIVITY_START_ALLOWED
                }
                context.startActivity(kioskIntent, options.toBundle())
            } else {
                context.startActivity(kioskIntent)
            }
        }

        // 4. Also trigger HOME intent so OEM launcher and System UI re-evaluate
        runCatching {
            context.startActivity(
                Intent(Intent.ACTION_MAIN)
                    .addCategory(Intent.CATEGORY_HOME)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            )
        }
    }

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
            features = KioskFeaturesDto(
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
        const val TAG = "BootReceiver"
    }
}
