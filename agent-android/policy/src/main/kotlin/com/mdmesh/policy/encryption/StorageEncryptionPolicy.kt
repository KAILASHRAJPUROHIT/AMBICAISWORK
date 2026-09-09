package com.mdmesh.policy.encryption

import android.app.admin.DevicePolicyManager
import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.wifi.DpmHandle

/**
 * Storage-encryption strategy via
 * [android.app.admin.DevicePolicyManager.setStorageEncryption] (available since API 11,
 * well below this project's minSdk 24, so no SDK gate beyond Device Owner is needed).
 * `setEnabled(false)` clears the requirement; it does not decrypt an already-encrypted
 * device (there is no API for that, and it would not be desirable on a fleet device).
 */
internal class StorageEncryptionPolicy(
    private val handle: DpmHandle,
) : EncryptionPolicy {

    override val capabilityKey: String = EncryptionPolicy.CAPABILITY_KEY

    override fun isSupported(): Boolean =
        handle.dpm.isDeviceOwnerApp(handle.admin.packageName)

    override fun setEnabled(enabled: Boolean): PolicyOutcome = runCatching {
        val status = handle.dpm.setStorageEncryption(handle.admin, enabled)
        if (!enabled) {
            return@runCatching PolicyOutcome.Applied
        }
        when (status) {
            DevicePolicyManager.ENCRYPTION_STATUS_ACTIVE,
            DevicePolicyManager.ENCRYPTION_STATUS_ACTIVE_PER_USER,
            DevicePolicyManager.ENCRYPTION_STATUS_ACTIVATING,
            -> PolicyOutcome.Applied
            else -> PolicyOutcome.Failed("device reports encryption status $status")
        }
    }.getOrElse { PolicyOutcome.Failed(it.message ?: "storageEncryption setEnabled failed") }
}
