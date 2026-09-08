package com.aradhanajewellers.smsrelay

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

/**
 * A visible, user-controlled foreground service. SMS delivery itself remains
 * event-driven through SmsReceiver; this service prevents vendor battery
 * managers from treating the configured relay as an idle background app.
 */
class RelayKeepAliveService : Service() {
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!RelayConfigStore(this).load().enabled) {
            stopSelf()
            return START_NOT_STICKY
        }
        createChannel()
        startForeground(NOTIFICATION_ID, NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentTitle("Aradhana SMS Relay active")
            .setContentText("Bank transaction SMS forwarding is armed")
            .setOngoing(true)
            .build())
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createChannel() {
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "SMS relay status", NotificationManager.IMPORTANCE_LOW)
        )
    }

    companion object {
        private const val CHANNEL_ID = "relay_keep_alive"
        private const val NOTIFICATION_ID = 8766
        fun start(context: Context) = ContextCompat.startForegroundService(context, Intent(context, RelayKeepAliveService::class.java))
        fun stop(context: Context) = context.stopService(Intent(context, RelayKeepAliveService::class.java))
    }
}
