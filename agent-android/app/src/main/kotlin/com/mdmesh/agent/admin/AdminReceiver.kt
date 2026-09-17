package com.mdmesh.agent.admin

import android.app.admin.DeviceAdminReceiver
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.PersistableBundle
import android.os.UserManager
import com.mdmesh.core.config.ServerConfigStore
import com.mdmesh.core.store.EnrollTokenStore
import com.mdmesh.core.sync.CheckInWorker
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Device-admin / Device-Owner receiver — the component named when binding the DPC
 * (`dpm set-device-owner com.mdmesh.agent/.admin.AdminReceiver`).
 *
 * Keep this thin: it reacts to admin lifecycle events and delegates real work to the
 * injected graph. The signing certificate of the app that owns this receiver is what
 * the DO binding is tied to — see the release signing note in `app/build.gradle.kts`.
 */
class AdminReceiver : DeviceAdminReceiver() {

    override fun onEnabled(context: Context, intent: Intent) {
        super.onEnabled(context, intent)
        // Deliberately no policy work here. Android runs this during Device Owner Setup Wizard;
        // some Android 16/OEM builds abort provisioning if a DPC mutates policy at this point.
        // MainActivity invokes DeviceOwnerInitializer after Setup Wizard has completed.
    }

    override fun onProfileProvisioningComplete(context: Context, intent: Intent) {
        super.onProfileProvisioningComplete(context, intent)
        // Android 12+ hands the QR bundle to AdminPolicyComplianceActivity, which returns
        // RESULT_OK before scheduling any post-setup work. Do not duplicate that work here:
        // this callback is still on Setup Wizard's critical path on Android 16.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) return

        // Legacy Android path: capture the QR credentials only after the callback returns.
        // Capture the server URL from the QR bundle BEFORE any check-in, so one prebuilt APK can
        // serve any deployment (it falls back to the baked URL only when absent — dev/ADB).
        ServerConfigStore(context.applicationContext).save(extrasString(intent, EXTRA_SERVER_URL))
        // Capture the single-use enroll token handed in via the QR provisioning bundle, then
        // trigger an immediate check-in so the device enrolls within seconds rather than on the
        // periodic cycle.
        val token = extrasToken(intent)
        val pending = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                if (!token.isNullOrBlank()) {
                    EnrollTokenStore(context.applicationContext).save(token)
                }
                CheckInWorker.schedule(context)
                CheckInWorker.scheduleNow(context)
            } finally {
                pending.finish()
            }
        }
    }

    /** Entering kiosk: block other apps/services from drawing toasts/dialogs over the kiosk. */
    override fun onLockTaskModeEntering(context: Context, intent: Intent, pkg: String) {
        super.onLockTaskModeEntering(context, intent, pkg)
        setCreateWindowsRestriction(context, restrict = true)
    }

    /** Leaving kiosk: allow overlays again. */
    override fun onLockTaskModeExiting(context: Context, intent: Intent) {
        super.onLockTaskModeExiting(context, intent)
        setCreateWindowsRestriction(context, restrict = false)
    }

    // FRP is applied only after the server has supplied this tenant's verified Google IDs.
    // Enrollment must not invent a recovery identity or rewrite an existing policy.

    private fun setCreateWindowsRestriction(context: Context, restrict: Boolean) {
        runCatching {
            val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
            if (!dpm.isDeviceOwnerApp(context.packageName)) return
            val admin = componentName(context)
            if (restrict) {
                dpm.addUserRestriction(admin, UserManager.DISALLOW_CREATE_WINDOWS)
            } else {
                dpm.clearUserRestriction(admin, UserManager.DISALLOW_CREATE_WINDOWS)
            }
        }
    }

    private fun extrasToken(intent: Intent): String? = extrasString(intent, EXTRA_ENROLL_TOKEN)

    @Suppress("DEPRECATION") // typed getParcelableExtra is API 33+; we support minSdk 24
    private fun extrasString(intent: Intent, key: String): String? {
        val bundle = intent.getParcelableExtra<PersistableBundle>(
            DevicePolicyManager.EXTRA_PROVISIONING_ADMIN_EXTRAS_BUNDLE,
        )
        return bundle?.getString(key)
    }

    companion object {
        /** Key in the QR `PROVISIONING_ADMIN_EXTRAS_BUNDLE` carrying the enroll token. */
        const val EXTRA_ENROLL_TOKEN = "com.mdmesh.ENROLL_TOKEN"

        /** Key carrying the server base URL, so one prebuilt APK serves any deployment. */
        const val EXTRA_SERVER_URL = "com.mdmesh.SERVER_URL"

        /** Constant fleet org id feeding the factory-reset-stable enrollment-specific id. */
        const val ORGANIZATION_ID = "mdmesh-fleet"

        /** This agent's admin component, used wherever a [ComponentName] is needed. */
        fun componentName(context: Context): ComponentName =
            ComponentName(context.applicationContext, AdminReceiver::class.java)
    }
}
