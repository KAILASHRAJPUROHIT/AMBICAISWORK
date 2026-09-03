package com.aradhanajewellers.smsrelay

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import java.security.MessageDigest
import java.text.DateFormat
import java.util.Date
import java.util.Properties
import javax.mail.Authenticator
import javax.mail.Message
import javax.mail.PasswordAuthentication
import javax.mail.Session
import javax.mail.Transport
import javax.mail.internet.InternetAddress
import javax.mail.internet.MimeMessage

class RelayWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val sender = inputData.getString(KEY_SENDER).orEmpty()
        val body = inputData.getString(KEY_BODY).orEmpty()
        val timestamp = inputData.getLong(KEY_TIMESTAMP, System.currentTimeMillis())
        val allowTest = inputData.getBoolean(KEY_ALLOW_TEST, false)
        val store = RelayConfigStore(applicationContext)
        val config = store.load()

        if (!config.enabled || !store.isValid(config) || (!allowTest &&
            !isBankTransactionMessage(sender, body, config.senderWhitelist))) {
            return Result.success()
        }

        val dedupeKey = sha256("$sender|$body")
        val dedupePrefs = applicationContext.getSharedPreferences("relay_dedupe", Context.MODE_PRIVATE)
        val previous = dedupePrefs.getLong(dedupeKey, 0L)
        if (previous > 0 && System.currentTimeMillis() - previous < DEDUPE_WINDOW_MS) return Result.success()

        return try {
            sendSmtp(config, sender, body, timestamp)
            dedupePrefs.edit().putLong(dedupeKey, System.currentTimeMillis()).apply()
            Result.success()
        } catch (_: Exception) {
            // WorkManager retries using a bounded exponential backoff. Never log SMS contents or credentials.
            Result.retry()
        }
    }

    private fun sendSmtp(config: RelayConfig, sender: String, body: String, timestamp: Long) {
        val ssl = config.smtpPort == 465
        val props = Properties().apply {
            put("mail.smtp.auth", "true")
            put("mail.smtp.host", config.smtpHost)
            put("mail.smtp.port", config.smtpPort.toString())
            put("mail.smtp.connectiontimeout", "20000")
            put("mail.smtp.timeout", "20000")
            put("mail.smtp.writetimeout", "20000")
            put("mail.smtp.ssl.enable", ssl.toString())
            put("mail.smtp.starttls.enable", (!ssl).toString())
            put("mail.smtp.starttls.required", (!ssl).toString())
        }
        val session = Session.getInstance(props, object : Authenticator() {
            override fun getPasswordAuthentication() = PasswordAuthentication(config.smtpUsername, config.smtpPassword)
        })
        val email = MimeMessage(session).apply {
            setFrom(InternetAddress(config.smtpUsername))
            setRecipients(Message.RecipientType.TO, InternetAddress.parse(config.recipient, false))
            subject = "[SMSForwarder] Bank SMS — $sender"
            setText(
                "From : $sender\n\n$body\n\n" +
                    "Relay timestamp: ${DateFormat.getDateTimeInstance().format(Date(timestamp))}\n" +
                    "Source: Aradhana SMS Relay",
                "UTF-8",
            )
        }
        Transport.send(email)
    }

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }

    companion object {
        const val KEY_SENDER = "sender"
        const val KEY_BODY = "body"
        const val KEY_TIMESTAMP = "timestamp"
        const val KEY_ALLOW_TEST = "allow_test"
        private const val DEDUPE_WINDOW_MS = 14L * 24 * 60 * 60 * 1000
    }
}
