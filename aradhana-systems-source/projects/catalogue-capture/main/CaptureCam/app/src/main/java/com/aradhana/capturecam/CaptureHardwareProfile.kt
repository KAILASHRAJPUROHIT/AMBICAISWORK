package com.aradhana.capturecam

import kotlin.math.min

/** Physical production rig. Manufacturer values are kept here instead of
 * being scattered through UI/servo code.
 *
 * Sources checked 2026-08-25:
 * - Sony ZV-E10 II: 23.3 x 15.5 mm APS-C, 6192 x 4128 stills.
 * - SELP16502 kit lens: 16-50 mm, 0.30 m tele minimum focus, 0.215x max.
 * - TYL stand: 250 x 400 mm, three rails spaced at 75 mm, seven supports.
 * - PULUZ PU5041B: 400 mm cube, 300 mm ceiling ring.
 */
object CaptureHardwareProfile {
    const val SENSOR_WIDTH_MM = 23.3f
    const val SENSOR_HEIGHT_MM = 15.5f
    const val STILL_WIDTH_PX = 6192
    const val STILL_HEIGHT_PX = 4128

    const val LENS_WIDE_MM = 16f
    const val LENS_TELE_MM = 50f
    const val TELE_MIN_FOCUS_MM = 300f
    const val TELE_MAX_MAGNIFICATION = 0.215f

    const val LIGHT_BOX_WIDTH_MM = 400f
    const val LIGHT_BOX_HEIGHT_MM = 400f
    const val LIGHT_BOX_DEPTH_MM = 400f
    const val LIGHT_RING_DIAMETER_MM = 300f

    const val STAND_WIDTH_MM = 250f
    const val STAND_HEIGHT_MM = 400f
    const val STAND_RAIL_SPACING_MM = 75f
    const val STAND_RAIL_COUNT = 3
    const val STAND_SUPPORT_COUNT = 7

    val TELE_CLOSEST_FIELD_WIDTH_MM: Float
        get() = SENSOR_WIDTH_MM / TELE_MAX_MAGNIFICATION
    val TELE_CLOSEST_FIELD_HEIGHT_MM: Float
        get() = SENSOR_HEIGHT_MM / TELE_MAX_MAGNIFICATION

    data class TelePlan(
        val requiredMagnification: Float,
        val appliedMagnification: Float,
        val estimatedCameraDistanceMm: Float,
        val requestedCompositionAchievable: Boolean,
        val projectedWidthFraction: Float,
        val projectedHeightFraction: Float,
        val projectedWidthPixels: Int,
        val projectedHeightPixels: Int
    )

    /** First-principles telephoto plan for a known displayed item size.
     * Distance is approximate until station calibration: compact internal-
     * focus lenses do not perfectly follow a thin-lens model. The maximum-
     * magnification and pixel projections are hard manufacturer limits. */
    fun telePlan(
        displayedWidthMm: Float,
        displayedHeightMm: Float,
        targetWidthFraction: Float,
        targetHeightFraction: Float
    ): TelePlan? {
        if (displayedWidthMm <= 0f || displayedHeightMm <= 0f) return null
        val widthMagnification = targetWidthFraction * SENSOR_WIDTH_MM / displayedWidthMm
        val heightMagnification = targetHeightFraction * SENSOR_HEIGHT_MM / displayedHeightMm
        val required = min(widthMagnification, heightMagnification)
        val applied = required.coerceAtMost(TELE_MAX_MAGNIFICATION)

        // Calibrate the thin-lens distance to Sony's published 300 mm MFD
        // at 0.215x. This yields a useful initial estimate; station setup
        // replaces it with measured camera-to-box-front geometry.
        val sonyMfdOffset = TELE_MIN_FOCUS_MM -
            LENS_TELE_MM * (1f + 1f / TELE_MAX_MAGNIFICATION)
        val estimatedDistance = LENS_TELE_MM * (1f + 1f / applied) + sonyMfdOffset
        val widthFraction = (displayedWidthMm * applied / SENSOR_WIDTH_MM).coerceAtMost(1f)
        val heightFraction = (displayedHeightMm * applied / SENSOR_HEIGHT_MM).coerceAtMost(1f)

        return TelePlan(
            requiredMagnification = required,
            appliedMagnification = applied,
            estimatedCameraDistanceMm = estimatedDistance,
            requestedCompositionAchievable = required <= TELE_MAX_MAGNIFICATION + 0.0001f,
            projectedWidthFraction = widthFraction,
            projectedHeightFraction = heightFraction,
            projectedWidthPixels = (widthFraction * STILL_WIDTH_PX).toInt(),
            projectedHeightPixels = (heightFraction * STILL_HEIGHT_PX).toInt()
        )
    }
}
