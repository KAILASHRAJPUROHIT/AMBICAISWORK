package com.mdmesh.policy.encryption

import com.mdmesh.policy.wifi.DpmHandle

/**
 * Selects the [EncryptionPolicy] strategy for the current device. Single candidate;
 * factory shape kept for uniformity. Returns `null` when no strategy is supported
 * (not Device Owner), in which case `storageEncryption` is never advertised.
 */
object EncryptionPolicyFactory {

    fun create(handle: DpmHandle): EncryptionPolicy? =
        listOf(StorageEncryptionPolicy(handle)).firstOrNull { it.isSupported() }
}
