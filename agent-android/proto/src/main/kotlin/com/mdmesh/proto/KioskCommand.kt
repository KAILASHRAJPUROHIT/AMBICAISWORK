package com.mdmesh.proto

import kotlinx.serialization.Serializable

/**
 * Payload of the `kiosk.enter` command (and the locally-persisted last-applied kiosk state).
 *
 * Every field defaults so old agents tolerate new keys and a minimal `{ }` payload is valid.
 *
 * @property mode `"single"` (pin one app) or `"launcher"` (show the allowed-apps home grid).
 * @property allowedPackages packages allowlisted for lock-task (the agent's own package is always added).
 * @property pinPackage in `single` mode, the app to launch + pin.
 * @property features lock-task UI feature toggles (see [com.mdmesh.kiosk.lockTaskFeatures]).
 * @property exitMode `"gesture"` | `"visible"` | `"remote"` — how a technician leaves kiosk on device.
 * @property password admin password required by the on-device exit (gesture/visible).
 * @property theme launcher appearance.
 * @property deviceLabel this device's console-assigned friendly name (e.g. "TAB1"), shown in the
 *   kiosk header in place of a generic app name. Null on older payloads/senders — the launcher
 *   falls back to a generic label rather than showing nothing.
 * @property orgName the deploying organisation's name (e.g. "Aradhana Jewellers"), shown under the
 *   device label. Null hides that line entirely rather than showing a placeholder.
 */
@Serializable
data class KioskApplyPayload(
    val mode: String = "launcher",
    val allowedPackages: List<String> = emptyList(),
    val pinPackage: String? = null,
    val features: KioskFeaturesDto = KioskFeaturesDto(),
    val exitMode: String = "gesture",
    val password: String? = null,
    val theme: KioskThemeDto = KioskThemeDto(),
    val deviceLabel: String? = null,
    val orgName: String? = null,
)

@Serializable
data class KioskFeaturesDto(
    val home: Boolean? = null,
    val recents: Boolean? = null,
    val notifications: Boolean? = null,
    val systemInfo: Boolean? = null,
    val keyguard: Boolean? = null,
    val lockButtons: Boolean? = null,
)

@Serializable
data class KioskThemeDto(
    val backgroundColor: String? = null,
    val textColor: String? = null,
    val iconSize: String? = null,
    /** Accent colour for kiosk chrome (status bar readout, exit affordance) — distinct from
     *  [textColor], which is the app-grid label colour. Null keeps the existing default. */
    val accentColor: String? = null,
)

/**
 * Payload of the `device.kioskTheme` command — restyles the currently-active kiosk without
 * re-picking apps or exit settings. Any null field leaves that part of the theme unchanged; the
 * agent merges this into the persisted [KioskApplyPayload.theme] and re-renders immediately via
 * the same reactive path [KioskApplyPayload] itself uses (no kiosk.enter round-trip). A no-op
 * (leaves the device idle) if no kiosk is currently active — there's no theme to restyle.
 */
@Serializable
data class KioskThemePayload(
    val backgroundColor: String? = null,
    val textColor: String? = null,
    val accentColor: String? = null,
)
