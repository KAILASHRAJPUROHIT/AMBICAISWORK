package com.mdmesh.core.permission

/**
 * All rows of the on-device permissions checklist
 * ([com.mdmesh.agent.PermissionsChecklistActivity]), in on-screen order (Device Admin first,
 * battery-optimization last since it's the one agents traditionally prompt for separately).
 */
object PermissionRegistry {
    fun checklist(): List<PermissionCheck> = listOf(
        DeviceAdminPermission,
        UsageAccessPermission,
        NotificationAccessPermission,
        UnknownSourcesPermission,
        OverlayPermission,
        WriteSettingsPermission,
        DisableAssistPermission,
        ExternalStoragePermission,
        BatteryOptimizationPermission,
    )
}
