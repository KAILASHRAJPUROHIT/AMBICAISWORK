package com.mdmesh.proto

/**
 * Open registry of device-action command types. By convention the action's command [type] is
 * identical to its capability token and to the server-side `requiresCapability` string, so there
 * is exactly one string per action and no drift between agent, server, and UI.
 *
 * The agent advertises [ADVERTISED_KEYS] in `capabilities.device`; the server flattens each into a
 * `device.<key>` token (see `AgentCapabilityTokens`).
 */
object DeviceAction {
    const val LOCK = "device.lock"
    const val REBOOT = "device.reboot"
    const val LOCKSCREEN_MESSAGE = "device.lockscreenMessage"
    const val ALERT = "device.alert"
    const val RING = "device.ring"
    const val RING_STOP = "device.ringStop"
    const val PASSCODE_RESET = "device.passcodeReset"
    const val WIPE = "device.wipe"

    /** Set the agent's connectivity power mode. Payload: `{ "mode": "adaptive" | "alwaysOn" }`. */
    const val POWER_MODE = "device.powerMode"

    /** Connectivity power-mode values (see [POWER_MODE]). */
    const val POWER_ADAPTIVE = "adaptive"
    const val POWER_ALWAYS_ON = "alwaysOn"

    /** Set how location is captured. Payload: `{ "mode": "passive" | "active" }`. */
    const val LOCATION_MODE = "device.locationMode"

    /** Location-mode values (see [LOCATION_MODE]). Passive = last-known (cheap); active = fresh fix. */
    const val LOCATION_PASSIVE = "passive"
    const val LOCATION_ACTIVE = "active"

    /** Enforce a minimum passcode quality/length. Payload: `{ "quality": "numeric" | "alphabetic" |
     *  "alphanumeric" | "complex" | "none", "minLength": 4 }`. */
    const val PASSWORD_QUALITY = "device.passwordQuality"

    /** Push a Wi-Fi network profile (distinct from the `wifi` toggle policy, which only does
     *  radio enable/disable). Payload: `{ "ssid": "...", "password": "...", "securityType": "wpa2" |
     *  "wpa3" | "open" }`. */
    const val WIFI_PROFILE = "device.wifiProfile"

    /** Install a CA certificate. Payload: `{ "certBase64": "..." }` — DER-encoded certificate
     *  bytes, base64-encoded. [android.app.admin.DevicePolicyManager.installCaCert] identifies
     *  the cert by its own bytes (no separate alias), so uninstall must resend the same bytes. */
    const val CERTIFICATE = "device.certificate"

    /** Push a home/lock screen wallpaper. Payload: `{ "url": "...", "target": "home" | "lock" |
     *  "both" }`. Needs only the normal (install-time, no runtime prompt) SET_WALLPAPER
     *  permission — unlike most device.* actions this doesn't need Device Owner at all. */
    const val WALLPAPER = "device.wallpaper"

    /** Restyle the currently-active kiosk (status bar/exit chrome colours) without a full
     *  kiosk.enter round-trip. Payload: [com.mdmesh.proto.KioskThemePayload] — any null field
     *  leaves that part of the theme unchanged. No-op if no kiosk is currently active. */
    const val KIOSK_THEME = "device.kioskTheme"

    /** Begin a time-boxed remote-view capture session. Payload: [RemoteSessionStartPayload].
     *  Gated separately from [ADVERTISED_KEYS] (Device-Owner only — see
     *  `CapabilityCollector`/AgentModule wiring) since it needs silently-grantable camera/mic
     *  permissions, unlike most `device.*` actions. */
    const val REMOTE_SESSION_START = "device.remoteSessionStart"

    /** End the current remote-view session immediately rather than waiting for its duration to
     *  elapse. No payload. Same capability gate as [REMOTE_SESSION_START]. */
    const val REMOTE_SESSION_STOP = "device.remoteSessionStop"

    /** Capability token (after `device.` prefix) for [REMOTE_SESSION_START]/[REMOTE_SESSION_STOP] —
     *  advertised separately from [ADVERTISED_KEYS], only when Device Owner. */
    const val REMOTE_SESSION_CAPABILITY_KEY = "remoteSession"

    /** Force-stop a runaway/misbehaving app immediately. Payload: `{ "packageName": "..." }`.
     *  Device-Owner only (uses [android.app.admin.DevicePolicyManager.setPackagesSuspended] as a
     *  kill primitive — suspending stops the target process immediately; un-suspending right after
     *  leaves it killed but launchable again, rather than permanently blocked). The handler
     *  hard-refuses to target the agent's own package under any circumstance — see
     *  `AppKillHandler`'s doc comment. Gated the same way as [REMOTE_SESSION_START]. */
    const val APP_KILL = "device.appKill"

    /** Capability token (after `device.` prefix) for [APP_KILL] — advertised separately from
     *  [ADVERTISED_KEYS], only when Device Owner. */
    const val APP_KILL_CAPABILITY_KEY = "appKill"

    /** Keys (after the `device.` prefix) advertised in `capabilities.device`. */
    val ADVERTISED_KEYS: List<String> = listOf(
        "lock", "reboot", "lockscreenMessage", "alert", "ring", "ringStop",
        "passcodeReset", "wipe", "powerMode", "locationMode",
        "passwordQuality", "wifiProfile", "certificate", "wallpaper", "kioskTheme",
    )
}
