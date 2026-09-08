package com.aradhanajewellers.smsrelay

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager

class SmsReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (Telephony.Sms.Intents.SMS_RECEIVED_ACTION != intent.action) return

        val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
        if (messages.isEmpty()) return

        val sender = messages.first().originatingAddress.orEmpty()
        val body = messages.joinToString(separator = "") { it.messageBody.orEmpty() }
        if (sender.isBlank() || body.isBlank()) return

        RelayScheduler.enqueue(context, sender, body, messages.first().timestampMillis)
    }
}

object RelayScheduler {
    fun enqueue(context: Context, sender: String, body: String, timestampMillis: Long, allowTest: Boolean = false) {
        val data = Data.Builder()
            .putString(RelayWorker.KEY_SENDER, sender)
            .putString(RelayWorker.KEY_BODY, body)
            .putLong(RelayWorker.KEY_TIMESTAMP, timestampMillis)
            .putBoolean(RelayWorker.KEY_ALLOW_TEST, allowTest)
            .build()
        val request = OneTimeWorkRequestBuilder<RelayWorker>().setInputData(data).build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            "sms-relay-${sender.hashCode()}-${timestampMillis}",
            ExistingWorkPolicy.KEEP,
            request,
        )
    }
}
