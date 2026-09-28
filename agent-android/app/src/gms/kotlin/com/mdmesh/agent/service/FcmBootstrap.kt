package com.mdmesh.agent.service

import android.content.Context
import android.util.Log
import com.google.firebase.messaging.FirebaseMessaging

/**
 * Starts FCM only on devices that actually have Google Play services. On a GMS-free China ROM
 * Firebase can't get a token anyway; leaving auto-init off avoids its background retries, and
 * the agent falls back to its WebSocket + WakeKeepAlive heartbeat like the old aosp build.
 */
object FcmBootstrap {
    fun start(context: Context) {
        val hasGms = runCatching {
            context.packageManager.getPackageInfo("com.google.android.gms", 0); true
        }.getOrDefault(false)
        Log.i("FcmBootstrap", "Google Play services present=$hasGms")
        if (hasGms) runCatching { FirebaseMessaging.getInstance().isAutoInitEnabled = true }
    }
}
