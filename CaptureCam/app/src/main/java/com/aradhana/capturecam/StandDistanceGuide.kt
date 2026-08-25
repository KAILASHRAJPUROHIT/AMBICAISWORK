package com.aradhana.capturecam

import kotlin.math.abs
import kotlin.math.min
import kotlin.math.sqrt

/**
 * Deterministic perspective guide for positioning the jewellery stand.
 *
 * For a fixed ornament, apparent linear size is proportional to
 * focal-length/distance. Therefore apparent bounding-box area is
 * proportional to (zoom/distance)^2. Using the currently detected box and
 * Sony's verified optical zoom range, this predicts the stand-distance ratio
 * needed to fill the requested frame area at maximum optical zoom:
 *
 *   targetDistance/currentDistance =
 *       (maxZoom/currentZoom) * sqrt(currentArea/targetArea)
 *
 * No scene model, depth sensor, network service, or local AI is involved.
 * Absolute centimetres require a measured reference distance; the live
 * closed-loop overlay does not. Staff move the stand in the indicated
 * direction until the ratio reaches 1.00 and the target frame turns green.
 */
object StandDistanceGuide {
    const val DESIRED_FRAME_AREA = 0.70f
    private const val SAFE_FRAME_DIMENSION = 0.92f
    private const val READY_RATIO_TOLERANCE = 0.06f
    private const val MIN_VALID_DIMENSION = 0.01f

    enum class Direction { CLOSER, FARTHER, READY }

    data class Guidance(
        val currentArea: Float,
        val targetArea: Float,
        val projectedAreaAtMaxZoom: Float,
        val rawDistanceRatio: Float,
        val targetWidth: Float,
        val targetHeight: Float,
        val maxZoom: Float
    )

    /** Returns null until the detector has a meaningful ornament box. */
    fun calculate(
        widthFraction: Float,
        heightFraction: Float,
        currentZoom: Float,
        maxZoom: Float,
        desiredArea: Float = DESIRED_FRAME_AREA,
        targetAspect: Float? = null
    ): Guidance? {
        if (!widthFraction.isFinite() || !heightFraction.isFinite() ||
            !currentZoom.isFinite() || !maxZoom.isFinite()
        ) return null
        if (widthFraction < MIN_VALID_DIMENSION || heightFraction < MIN_VALID_DIMENSION ||
            currentZoom <= 0f || maxZoom < currentZoom
        ) return null

        val width = widthFraction.coerceIn(MIN_VALID_DIMENSION, 1f)
        val height = heightFraction.coerceIn(MIN_VALID_DIMENSION, 1f)
        val currentArea = (width * height).coerceIn(0.0001f, 1f)

        // Once the tag is known, use that stock category's researched
        // silhouette instead of preserving a possibly partial/noisy gold
        // blob's aspect ratio. Unknown categories retain the detector ratio.
        val aspect = targetAspect?.takeIf { it.isFinite() && it > 0f }
            ?: (width / height)
        var targetWidth = sqrt(desiredArea.coerceIn(0.005f, 0.90f) * aspect)
        var targetHeight = sqrt(desiredArea.coerceIn(0.005f, 0.90f) / aspect)
        val safeScale = min(
            SAFE_FRAME_DIMENSION / targetWidth,
            SAFE_FRAME_DIMENSION / targetHeight
        ).coerceAtMost(1f)
        targetWidth *= safeScale
        targetHeight *= safeScale
        val targetArea = (targetWidth * targetHeight).coerceIn(0.0001f, 1f)

        val zoomGain = maxZoom / currentZoom
        val projectedAtMax = (currentArea * zoomGain * zoomGain).coerceAtMost(1f)
        val distanceRatio = (zoomGain * sqrt(currentArea / targetArea)).coerceIn(0.05f, 4f)

        return Guidance(
            currentArea = currentArea,
            targetArea = targetArea,
            projectedAreaAtMaxZoom = projectedAtMax,
            rawDistanceRatio = distanceRatio,
            targetWidth = targetWidth,
            targetHeight = targetHeight,
            maxZoom = maxZoom
        )
    }

    fun direction(distanceRatio: Float): Direction = when {
        distanceRatio < 1f - READY_RATIO_TOLERANCE -> Direction.CLOSER
        distanceRatio > 1f + READY_RATIO_TOLERANCE -> Direction.FARTHER
        else -> Direction.READY
    }

    fun changePercent(distanceRatio: Float): Int =
        (abs(1f - distanceRatio) * 100f).toInt().coerceIn(0, 95)

    fun message(guidance: Guidance, smoothedDistanceRatio: Float): String {
        val current = (guidance.currentArea * 100f).toInt().coerceIn(0, 100)
        val target = (guidance.targetArea * 100f).toInt().coerceIn(0, 100)
        val projected = (guidance.projectedAreaAtMaxZoom * 100f).toInt().coerceIn(0, 100)
        val targetDistance = (smoothedDistanceRatio * 100f).toInt().coerceIn(5, 400)
        return when (direction(smoothedDistanceRatio)) {
            Direction.CLOSER ->
                "▼ MOVE STAND CLOSER ${changePercent(smoothedDistanceRatio)}%  •  " +
                    "target distance ≈ $targetDistance% of current  •  " +
                    "frame $current% → $target% at ${"%.1f".format(guidance.maxZoom)}× max"
            Direction.FARTHER ->
                "▲ MOVE STAND FARTHER ${changePercent(smoothedDistanceRatio)}%  •  " +
                    "target distance ≈ $targetDistance% of current  •  " +
                    "max-zoom projection $projected% / target $target%"
            Direction.READY ->
                "✓ STAND DISTANCE READY  •  max optical ${"%.1f".format(guidance.maxZoom)}×  •  " +
                    "target frame $target%"
        }
    }
}
