package com.mdmesh.policy.encryption

import com.mdmesh.policy.PolicyOutcome
import com.mdmesh.policy.TogglePolicy

/**
 * Capability-abstracted storage-encryption requirement.
 *
 * `setEnabled(true)` requires full-disk encryption via
 * [android.app.admin.DevicePolicyManager.setStorageEncryption]. On modern Android
 * (API 24+, this project's minSdk) storage is encrypted by default at first boot, so
 * this is mostly a compliance *assertion* — it fails closed (returns
 * [PolicyOutcome.Failed]) if the device reports it cannot honour the requirement,
 * rather than silently accepting an unencrypted device. The single concrete strategy
 * ([StorageEncryptionPolicy]) is selected by [EncryptionPolicyFactory].
 */
interface EncryptionPolicy : TogglePolicy {

    override fun setEnabled(enabled: Boolean): PolicyOutcome

    companion object {
        const val CAPABILITY_KEY = "storageEncryption"
    }
}
