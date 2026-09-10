package com.mdmesh.agent

import android.service.notification.NotificationListenerService

/**
 * Deliberately inert — no `onNotificationPosted`/`onNotificationRemoved` override, reads
 * nothing. Exists solely so [com.mdmesh.core.permission.NotificationAccessPermission]'s OS
 * toggle is grantable. Unlike the accessibility services in this app (which ship
 * `android:enabled="false"` and get armed at runtime because arming them changes real
 * behavior), this listener is already inert by construction — there's no separate "off" state
 * to gate, the system's own per-app notification-access toggle already governs it entirely.
 */
class NotificationAccessListenerService : NotificationListenerService()
