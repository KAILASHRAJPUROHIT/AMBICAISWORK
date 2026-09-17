package com.mdmesh.agent.provisioning

import android.app.Activity
import android.app.admin.DevicePolicyManager
import android.os.Bundle
import android.os.PersistableBundle
import com.mdmesh.agent.admin.AdminReceiver
import com.mdmesh.core.config.ServerConfigStore
import com.mdmesh.core.store.EnrollTokenStore
import com.mdmesh.core.sync.CheckInWorker
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Handles `ACTION_ADMIN_POLICY_COMPLIANCE`, launched right after provisioning.
 *
 * On Android 12+ (the modern provisioning contract) the `PROVISIONING_ADMIN_EXTRAS_BUNDLE`
 * — which carries our single-use enroll token and the deployment's server URL — is delivered
 * to THIS activity's intent, not to [AdminReceiver.onProfileProvisioningComplete]. So this is
 * where we capture both. This activity must return immediately: running policy or networking
 * work while Setup Wizard is finalising Device Owner state is unreliable on OEM builds.
 */
class AdminPolicyComplianceActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val ctx = applicationContext
        // Server URL first (synchronous SharedPreferences), so no check-in scheduled below can
        // ever run against the baked fallback. save() is a no-op for an absent/blank extra.
        ServerConfigStore(ctx).save(extrasString(AdminReceiver.EXTRA_SERVER_URL))
        val token = extrasString(AdminReceiver.EXTRA_ENROLL_TOKEN)
        // Signal compliance before any asynchronous enrollment work. A failed background check-in
        // can retry; a failure before this result makes Setup Wizard erase the device.
        setResult(RESULT_OK)
        finish()

        if (!token.isNullOrBlank()) {
            // Independent process scope: token persistence and server contact happen after the
            // provisioning result, never on Setup Wizard's critical path.
            CoroutineScope(Dispatchers.IO).launch {
                EnrollTokenStore(ctx).save(token)
                runCatching { CheckInWorker.scheduleNow(ctx) }
            }
        }
    }

    @Suppress("DEPRECATION") // typed getParcelableExtra is API 33+; we support minSdk 24
    private fun extrasString(key: String): String? =
        intent.getParcelableExtra<PersistableBundle>(
            DevicePolicyManager.EXTRA_PROVISIONING_ADMIN_EXTRAS_BUNDLE,
        )?.getString(key)
}
