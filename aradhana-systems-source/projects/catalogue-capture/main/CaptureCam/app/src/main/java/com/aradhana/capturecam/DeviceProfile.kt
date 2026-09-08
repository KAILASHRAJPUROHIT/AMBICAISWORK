package com.aradhana.capturecam

import android.content.SharedPreferences
import android.os.Build
import android.util.Log

/**
 * Per-tablet hardware facts the app cannot infer at runtime.
 *
 * The macro physical camera ID is the clearest example: on the Redmi Pad 2 Pro
 * the back logical camera exposes physId 4 as a genuine macro sensor, which is
 * what makes tag scanning sharp at ~10cm. A different tablet enumerates
 * different physical IDs, so a value hardcoded for one device is wrong on the
 * next -- and silently so, because binding falls back to the default sensor.
 *
 * Detection is by Build.MODEL, with an explicit operator override stored in
 * preferences for when a new device is not yet in the table, or is detected
 * wrongly. AUTO is the default and is what should normally be used.
 */
object DeviceProfile {

    const val PREF_KEY = "device_profile_index"

    data class Profile(
        val label: String,
        /** Build.MODEL values this profile matches. Empty = never auto-matches. */
        val models: Set<String>,
        /**
         * Physical camera ID to pin for macro tag capture, or null to let
         * CameraX bind the default back sensor. Always validated against the
         * device's real physical IDs before use -- an ID listed here that the
         * hardware does not expose is ignored, not forced.
         */
        val macroPhysicalCameraId: String?,
    )

    /** Index 0 is AUTO; the rest are explicit overrides, in dropdown order. */
    val PROFILES: List<Profile> = listOf(
        Profile("Auto-detect", emptySet(), null),
        Profile("Redmi Pad 2", setOf("2505DRP06I"), null),
        Profile("Redmi Pad 2 Pro", setOf("2509BRP2DI"), "4"),
        Profile("Other tablet (no macro pin)", emptySet(), null),
    )

    val LABELS: Array<String> get() = PROFILES.map { it.label }.toTypedArray()

    /** The profile in force: an explicit override, else the model match. */
    fun active(prefs: SharedPreferences): Profile {
        val index = prefs.getInt(PREF_KEY, 0)
        if (index in 1..PROFILES.lastIndex) return PROFILES[index]
        return detected()
    }

    /** Profile matching this hardware, or a safe unpinned default. */
    fun detected(): Profile {
        val model = Build.MODEL?.trim().orEmpty()
        val match = PROFILES.firstOrNull { model in it.models }
        if (match == null) {
            Log.i(
                "DeviceProfile",
                "No profile for Build.MODEL='$model' -- defaulting to no macro pin. " +
                    "Add it to DeviceProfile.PROFILES once its physical camera IDs are known."
            )
            return PROFILES.last()
        }
        return match
    }

    /** What the settings screen shows next to "Auto-detect". */
    fun detectedLabel(): String = "${detected().label} (${Build.MODEL})"
}
