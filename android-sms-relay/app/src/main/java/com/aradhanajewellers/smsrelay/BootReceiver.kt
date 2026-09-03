package com.aradhanajewellers.smsrelay

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Re-arms the foreground relay after a device reboot or app update. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (RelayConfigStore(context).load().enabled) {
            // Some newer Android releases restrict foreground-service starts
            // during BOOT_COMPLETED. SMS_RECEIVED remains registered by the OS;
            // avoid a receiver crash if the vendor defers the visible service.
            runCatching { RelayKeepAliveService.start(context) }
        }
    }
}
