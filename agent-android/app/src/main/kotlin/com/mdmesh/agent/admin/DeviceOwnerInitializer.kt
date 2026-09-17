package com.mdmesh.agent.admin

import android.Manifest
import android.app.admin.DevicePolicyManager
import android.content.Context
import android.os.Build
import com.mdmesh.core.action.ResetPasswordTokenStore
import com.mdmesh.policy.PolicyManager
import com.mdmesh.policy.wifi.DpmHandle

/**
 * Device-Owner baseline applied only after Android has completed Setup Wizard.
 *
 * Do not call this from [AdminReceiver] provisioning callbacks: several Android 16/OEM setup
 * flows abort Device Owner provisioning when a DPC changes policy before Setup Wizard finishes.
 */
object DeviceOwnerInitializer {

    fun apply(context: Context) {
        val appContext = context.applicationContext
        val dpm = appContext.getSystemService(Context.DEVICE_POLICY_SERVICE) as? DevicePolicyManager ?: return
        if (!dpm.isDeviceOwnerApp(appContext.packageName)) return
        val admin = AdminReceiver.componentName(appContext)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            runCatching { dpm.setOrganizationId("mdmesh-fleet") }
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            runCatching { dpm.setUserControlDisabledPackages(admin, listOf(appContext.packageName)) }
            runCatching { dpm.setLocationEnabled(admin, true) }
        }

        val handle = DpmHandle(dpm, admin, appContext)
        runCatching { PolicyManager(handle).setPermissionAutoGrant() }
        runCatching { ResetPasswordTokenStore(appContext, handle).ensureToken() }
        val permissions = buildList {
            add(Manifest.permission.READ_PHONE_STATE)
            add(Manifest.permission.READ_PHONE_NUMBERS)
            add(Manifest.permission.ACCESS_FINE_LOCATION)
            add(Manifest.permission.ACCESS_COARSE_LOCATION)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) add(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
        }
        permissions.forEach { permission ->
            runCatching {
                dpm.setPermissionGrantState(
                    admin,
                    appContext.packageName,
                    permission,
                    DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED,
                )
            }
        }
    }
}
