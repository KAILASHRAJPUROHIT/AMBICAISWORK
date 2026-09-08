package com.mdmesh.proto

import java.security.MessageDigest

/**
 * Mirrors the server's admin-login hash scheme exactly (`common/.../PasswordUtil.java`:
 * `SHA1(MD5(raw) + PASS_SALT)`, salt `"5YdSYHyg2U"`), so the fleet-wide admin passcode set in the
 * web Settings page and delivered as [AgentCheckInResponse.adminPasscodeHash] can be verified
 * on-device without ever transmitting the raw passcode back to the server.
 */
object PasscodeHash {
    private const val SALT = "5YdSYHyg2U"

    fun of(raw: String): String {
        // Case matters here: the MD5 hex string is itself hashed again, and the server
        // (CryptoUtil.getHexString) uppercases it before appending the salt.
        val md5 = digest("MD5", raw.toByteArray(Charsets.UTF_8)).toHex().uppercase()
        return digest("SHA-1", (md5 + SALT).toByteArray(Charsets.UTF_8)).toHex()
    }

    fun matches(raw: String, expectedHash: String): Boolean =
        of(raw).equals(expectedHash, ignoreCase = true)

    private fun digest(algorithm: String, bytes: ByteArray): ByteArray =
        MessageDigest.getInstance(algorithm).digest(bytes)

    private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }
}
