package com.mdmesh.core.config

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * The device's current Firebase Cloud Messaging registration token, so it can be attached to
 * every check-in (see [com.mdmesh.core.sync.CheckInCoordinator]) without waiting on an async
 * Firebase call mid-request. Populated by the FCM SDK's own callback
 * (`com.mdmesh.agent.AmbicFirebaseMessagingService.onNewToken`) - null until Firebase has
 * actually issued one (no config yet, no Play Services, or the very first launch before the SDK
 * has called back).
 *
 * SharedPreferences-backed for the same reason as [ServerConfigStore]: a synchronous read on the
 * check-in path, no coroutine needed just to build the request body.
 */
@Singleton
class FcmTokenStore @Inject constructor(@ApplicationContext context: Context) {
    private val prefs = context.getSharedPreferences("mdm_fcm", Context.MODE_PRIVATE)

    fun get(): String? = prefs.getString(KEY, null)?.takeIf { it.isNotBlank() }

    fun save(token: String?) {
        val t = token?.trim()?.takeIf { it.isNotBlank() } ?: return
        prefs.edit().putString(KEY, t).apply()
    }

    private companion object { const val KEY = "token" }
}
