package com.mdmesh.core.permission

import android.content.Context
import android.content.Intent
import android.provider.Settings
import androidx.core.app.NotificationManagerCompat

/**
 * Backed by `com.mdmesh.agent.NotificationAccessListenerService` — a deliberately inert
 * `NotificationListenerService` (no `onNotificationPosted`/`onNotificationRemoved` overrides,
 * reads nothing) that exists solely so this OS toggle is grantable today. The grant itself is
 * real and broad even though this implementation doesn't use it yet; the on-device description
 * is intentionally honest about that rather than implying it's a no-op.
 */
object NotificationAccessPermission : PermissionCheck {
    override val key = "notificationAccess"
    override val label = "Enable App Notifications"
    override val description =
        "Grants notification-listener access. Not yet used to act on notification content — reserved for a future feature."
    override val verifiable = true
    override val skippable = true

    override fun isGranted(context: Context): Boolean =
        NotificationManagerCompat.getEnabledListenerPackages(context).contains(context.packageName)

    override fun settingsIntent(context: Context): Intent =
        Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
}
