package com.mdmesh.agent.provisioning

import android.app.Activity
import android.app.admin.DevicePolicyManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.core.content.ContextCompat
import com.mdmesh.agent.service.CheckInService
import com.mdmesh.agent.service.WakeKeepAlive
import com.mdmesh.core.config.ServerConfigStore
import com.mdmesh.core.store.DeviceIdStore
import com.mdmesh.core.store.EnrollTokenStore
import com.mdmesh.core.sync.CheckInWorker
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * AOSP-only USB bootstrap endpoint used by the AMBIC provisioner after `dpm set-device-owner`.
 *
 * It is intentionally unavailable in the GMS APK. An adb caller must supply a tenant-minted,
 * single-use token; the endpoint refuses a non-DO or an already enrolled device, so it cannot
 * retarget a live managed device. It has no UI and finishes immediately after scheduling sync.
 */
class AospUsbBootstrapActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val serverUrl = intent.getStringExtra(EXTRA_SERVER_URL)?.trim()
        val enrollToken = intent.getStringExtra(EXTRA_ENROLL_TOKEN)?.trim()
        if (!isDeviceOwner() || !serverUrl.isValidServerUrl() || enrollToken.isNullOrBlank()) {
            finish()
            return
        }

        CoroutineScope(Dispatchers.IO).launch {
            // Never overwrite a completed enrollment with another operator's token.
            if (DeviceIdStore(applicationContext).current().isNullOrBlank()) {
                ServerConfigStore(applicationContext).save(serverUrl)
                EnrollTokenStore(applicationContext).save(enrollToken)
                CheckInWorker.schedule(applicationContext)
                CheckInWorker.scheduleNow(applicationContext)
                WakeKeepAlive.schedule(applicationContext)
                ContextCompat.startForegroundService(
                    applicationContext,
                    Intent(applicationContext, CheckInService::class.java),
                )
            }
            finish()
        }
    }

    private fun isDeviceOwner(): Boolean =
        (getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager)
            .isDeviceOwnerApp(packageName)

    private fun String?.isValidServerUrl(): Boolean =
        this?.let { runCatching { android.net.Uri.parse(it) }.getOrNull() }
            ?.let { it.scheme == "https" && !it.host.isNullOrBlank() } == true

    private companion object {
        const val EXTRA_SERVER_URL = "com.mdmesh.aosp.SERVER_URL"
        const val EXTRA_ENROLL_TOKEN = "com.mdmesh.aosp.ENROLL_TOKEN"
    }
}
