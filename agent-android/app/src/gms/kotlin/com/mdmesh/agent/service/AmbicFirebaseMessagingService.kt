package com.mdmesh.agent.service

import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.mdmesh.core.config.FcmTokenStore
import com.mdmesh.core.sync.CheckInWorker
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

/** GMS-only Doze wake channel. The AOSP distribution uses its persistent socket and heartbeat. */
@AndroidEntryPoint
class AmbicFirebaseMessagingService : FirebaseMessagingService() {

    @Inject lateinit var tokenStore: FcmTokenStore

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        tokenStore.save(token)
        runCatching { CheckInWorker.scheduleNow(applicationContext) }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)
        if (message.data.containsKey("wake")) {
            runCatching { CheckInWorker.scheduleNow(applicationContext) }
        }
    }
}
