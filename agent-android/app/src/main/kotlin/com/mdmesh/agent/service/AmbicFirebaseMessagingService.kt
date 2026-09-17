package com.mdmesh.agent.service

import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.mdmesh.core.config.FcmTokenStore
import com.mdmesh.core.sync.CheckInWorker
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

/**
 * Second wake channel alongside the agent's own WebSocket ([TransportManager]/[CheckInService]):
 * where the WebSocket is killed by Doze or an OEM's own battery manager (notably MIUI) once the
 * screen is off, Google Play Services keeps its own connection alive specifically for
 * high-priority FCM delivery, so a data message still reaches a sleeping device. The payload
 * carries no command content - `{"wake": "commands"|"interactive"}`, same shape as
 * [com.hmdm.notification.AgentWakeHub]'s WebSocket signal - so a leaked/replayed message reveals
 * nothing; it only triggers the SAME authenticated check-in the device would run anyway.
 *
 * Registered in AndroidManifest.xml. Requires google-services.json + the
 * com.google.gms.google-services Gradle plugin (not yet applied - see app/build.gradle.kts) to
 * actually receive anything; until then this class exists but the FCM SDK has nothing to deliver
 * to it.
 */
@AndroidEntryPoint
class AmbicFirebaseMessagingService : FirebaseMessagingService() {

    @Inject lateinit var tokenStore: FcmTokenStore

    /** Called on first install, on token rotation, and after any local data clear - store it so
     *  the next check-in reports it (see CheckInCoordinator), regardless of whether this device is
     *  even enrolled yet. */
    override fun onNewToken(token: String) {
        super.onNewToken(token)
        tokenStore.save(token)
        runCatching { CheckInWorker.scheduleNow(applicationContext) }
    }

    /** Data-only wake message (never a "notification" payload - nothing should appear in the
     *  system tray for this). Whatever "wake" says, the response is the same: run a real
     *  check-in, which pulls whatever's actually pending server-side. */
    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)
        if (message.data.containsKey("wake")) {
            runCatching { CheckInWorker.scheduleNow(applicationContext) }
        }
    }
}
