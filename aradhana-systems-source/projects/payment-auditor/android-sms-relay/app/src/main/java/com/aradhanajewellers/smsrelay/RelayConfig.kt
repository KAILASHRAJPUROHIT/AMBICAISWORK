package com.aradhanajewellers.smsrelay

import android.content.Context
import java.security.SecureRandom
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

data class RelayConfig(
    val enabled: Boolean,
    val forwardAllMessages: Boolean,
    val smtpHost: String,
    val smtpPort: Int,
    val smtpUsername: String,
    val smtpPassword: String,
    val recipient: String,
    val senderWhitelist: List<String>,
)

class RelayConfigStore(context: Context) {
    private val prefs = EncryptedSharedPreferences.create(
        context,
        "aradhana_sms_relay",
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    fun load(): RelayConfig = RelayConfig(
        enabled = prefs.getBoolean(KEY_ENABLED, false),
        // Older releases could enable all-SMS forwarding. Never restore that
        // setting: the relay is strictly limited to bank transactions.
        forwardAllMessages = false,
        smtpHost = prefs.getString(KEY_SMTP_HOST, "smtp.gmail.com") ?: "smtp.gmail.com",
        smtpPort = prefs.getInt(KEY_SMTP_PORT, 465),
        smtpUsername = prefs.getString(KEY_SMTP_USERNAME, "") ?: "",
        smtpPassword = prefs.getString(KEY_SMTP_PASSWORD, "") ?: "",
        recipient = prefs.getString(KEY_RECIPIENT, "") ?: "",
        senderWhitelist = (prefs.getString(KEY_SENDER_WHITELIST, "") ?: "")
            .lines().map { it.trim() }.filter { it.isNotEmpty() },
    )

    fun save(config: RelayConfig) {
        prefs.edit()
            .putBoolean(KEY_ENABLED, config.enabled)
            .putBoolean(KEY_FORWARD_ALL_MESSAGES, false)
            .putString(KEY_SMTP_HOST, config.smtpHost.trim())
            .putInt(KEY_SMTP_PORT, config.smtpPort)
            .putString(KEY_SMTP_USERNAME, config.smtpUsername.trim())
            .putString(KEY_SMTP_PASSWORD, config.smtpPassword)
            .putString(KEY_RECIPIENT, config.recipient.trim())
            .putString(KEY_SENDER_WHITELIST, config.senderWhitelist.joinToString("\n"))
            .apply()
    }

    fun isValid(config: RelayConfig): Boolean =
        config.smtpHost.isNotBlank() && config.smtpPort in 1..65535 &&
            config.smtpUsername.isNotBlank() && config.smtpPassword.isNotBlank() &&
            config.recipient.contains("@")

    fun pairingCode(): String {
        val existing = prefs.getString(KEY_PAIRING_CODE, "") ?: ""
        if (existing.isNotBlank()) return existing
        return rotatePairingCode()
    }

    fun rotatePairingCode(): String {
        val alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        val random = SecureRandom()
        val code = (1..8).joinToString("") { alphabet[random.nextInt(alphabet.length)].toString() }
        prefs.edit().putString(KEY_PAIRING_CODE, code).apply()
        return code
    }

    companion object {
        private const val KEY_ENABLED = "enabled"
        private const val KEY_FORWARD_ALL_MESSAGES = "forward_all_messages"
        private const val KEY_SMTP_HOST = "smtp_host"
        private const val KEY_SMTP_PORT = "smtp_port"
        private const val KEY_SMTP_USERNAME = "smtp_username"
        private const val KEY_SMTP_PASSWORD = "smtp_password"
        private const val KEY_RECIPIENT = "recipient"
        private const val KEY_SENDER_WHITELIST = "sender_whitelist"
        private const val KEY_PAIRING_CODE = "pairing_code"
    }
}

fun matchesApprovedSender(sender: String, patterns: List<String>): Boolean {
    val value = sender.trim().uppercase()
    return patterns.any { raw ->
        val pattern = raw.trim().uppercase()
        when {
            pattern.endsWith("*") -> value.startsWith(pattern.dropLast(1))
            else -> value == pattern
        }
    }
}

/**
 * Bank alerts vary widely by issuer. Require a transaction direction and an
 * amount, then either a banking identifier in the body or an approved sender.
 * This catches unknown-bank alerts while excluding OTPs and ordinary SMS.
 */
fun isBankTransactionMessage(sender: String, body: String, trustedSenders: List<String>): Boolean {
    val text = body.uppercase()
    val direction = Regex("\\b(CREDIT(?:ED)?|DEBIT(?:ED)?|WITHDRAWN|SPENT|PAID)\\b").containsMatchIn(text)
    val amount = Regex("(?:INR|RS\\.?|₹)\\s*[0-9][0-9,]*(?:\\.[0-9]{1,2})?|\\b(?:AMOUNT(?:\\s+OF)?|CREDIT(?:ED)?|DEBIT(?:ED)?)\\b[^\\n]{0,40}?\\b[0-9][0-9,]*(?:\\.[0-9]{1,2})?").containsMatchIn(text)
    val bankEvidence = Regex("\\b(A/?C|ACCOUNT|UPI|IMPS|NEFT|RTGS|UTR|REF(?:ERENCE)?|TRANSACTION|TXN|CARD|ATM|POS|NACH|ECS|IFSC|BANK)\\b").containsMatchIn(text)
    return direction && amount && (bankEvidence || matchesApprovedSender(sender, trustedSenders))
}
