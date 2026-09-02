package com.aradhanajewellers.smsrelay

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

class WifiConfigService : Service() {
    private lateinit var server: WifiConfigServer

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        createChannel()
        startForeground(NOTIFICATION_ID, NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentTitle("Aradhana SMS Relay Wi-Fi settings")
            .setContentText("Local settings access is active on port ${WifiConfigServer.PORT}")
            .setOngoing(true)
            .build())
        server = WifiConfigServer(this)
        server.start()
        running = true
        return START_NOT_STICKY
    }

    override fun onDestroy() { if (::server.isInitialized) server.stop(); running = false; super.onDestroy() }
    override fun onBind(intent: Intent?): IBinder? = null

    private fun createChannel() {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "SMS relay Wi-Fi settings", NotificationManager.IMPORTANCE_LOW))
    }

    companion object {
        private const val CHANNEL_ID = "wifi_config"
        private const val NOTIFICATION_ID = 8765
        @Volatile var running = false
        fun start(context: Context) = ContextCompat.startForegroundService(context, Intent(context, WifiConfigService::class.java))
        fun stop(context: Context) = context.stopService(Intent(context, WifiConfigService::class.java))
    }
}
