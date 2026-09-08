package com.aradhana.capturecam

import kotlin.math.abs

/**
 * Conservative closed-loop controller for deterministic Sony gold tracking.
 *
 * Output is at most one physical action per decision: pan, tilt, optical
 * zoom, or Sony half-press autofocus. Zoom-in is forbidden until the target
 * is centered and measured sharp after autofocus. No shutter command exists
 * here. Pan/tilt have cumulative budgets because the RSC 2 exposes velocity
 * bursts rather than absolute position feedback.
 */
class SonyGoldServoController {

    sealed class Command {
        data class Pan(val sign: Int, val durationMs: Long) : Command()
        data class Tilt(val sign: Int, val durationMs: Long) : Command()
        data class Zoom(val tele: Boolean, val durationMs: Long) : Command()
        data class Focus(val durationMs: Long) : Command()
    }

    data class Observation(
        val frameId: Long,
        val bounds: MaterialDetector.Bounds,
        val pointCount: Int,
        val scale: Float,
        val sharpness: Float
    )

    data class Decision(
        val command: Command?,
        val status: String,
        val centerX: Float?,
        val centerY: Float?,
        val coverage: Float,
        val detectionStable: Boolean
    )

    private var emaX: Float? = null
    private var emaY: Float? = null
    private var detectionStreak = 0
    private var lossStreak = 0
    private var centeredStreak = 0
    private var nextActionAt = 0L
    private var panOffsetMs = 0
    private var tiltOffsetMs = 0
    private var lastObservationFrameId = -1L
    private var focusNeeded = true
    private var focusConfirmed = false
    private var focusAttempts = 0
    private var focusConfirmFramesRemaining = 0
    private var zoomInBursts = 0
    private var zoomOutBursts = 0
    private val sharpnessWindow = ArrayDeque<Float>()

    fun reset() {
        emaX = null
        emaY = null
        detectionStreak = 0
        lossStreak = 0
        centeredStreak = 0
        nextActionAt = 0L
        panOffsetMs = 0
        tiltOffsetMs = 0
        lastObservationFrameId = -1L
        focusNeeded = true
        focusConfirmed = false
        focusAttempts = 0
        focusConfirmFramesRemaining = 0
        zoomInBursts = 0
        zoomOutBursts = 0
        sharpnessWindow.clear()
    }

    fun onFrame(
        observation: Observation?,
        nowMs: Long,
        gimbalReady: Boolean,
        gimbalMoving: Boolean
    ): Decision {
        if (observation == null || observation.pointCount < MIN_GOLD_POINTS) {
            detectionStreak = 0
            centeredStreak = 0
            lossStreak += 1
            if (lossStreak >= LOSS_RESET_FRAMES) {
                emaX = null
                emaY = null
            }
            return Decision(null, "Searching for isolated gold in center guide…", null, null, 0f, false)
        }

        val bounds = observation.bounds
        val isNewFrame = observation.frameId != lastObservationFrameId
        if (isNewFrame) {
            lastObservationFrameId = observation.frameId
            sharpnessWindow.addLast(observation.sharpness)
            while (sharpnessWindow.size > SHARPNESS_WINDOW_SIZE) sharpnessWindow.removeFirst()
            if (focusConfirmFramesRemaining > 0) focusConfirmFramesRemaining -= 1
            detectionStreak += 1
        }

        lossStreak = 0
        val rawX = (bounds.x0 + bounds.x1) / 2f
        val rawY = (bounds.y0 + bounds.y1) / 2f
        emaX = emaX?.let { it + (rawX - it) * EMA_ALPHA } ?: rawX
        emaY = emaY?.let { it + (rawY - it) * EMA_ALPHA } ?: rawY
        val cx = emaX!!
        val cy = emaY!!
        val dx = cx - 0.5f
        val dy = cy - 0.5f
        val scale = observation.scale
        val stable = detectionStreak >= REQUIRED_DETECTION_FRAMES
        val centered = abs(dx) <= CENTER_DEADBAND && abs(dy) <= CENTER_DEADBAND
        if (isNewFrame) centeredStreak = if (centered) centeredStreak + 1 else 0

        if (!stable) {
            return Decision(null, "Gold detected — confirming target…", cx, cy, scale, false)
        }
        if (gimbalMoving || nowMs < nextActionAt) {
            return Decision(null, "Tracking gold…", cx, cy, scale, true)
        }

        // Recover field of view before steering on clipped geometry.
        if (MaterialDetector.touchesFrameEdge(bounds, EDGE_MARGIN) || scale > MAX_TARGET_SCALE) {
            if (zoomOutBursts >= MAX_ZOOM_OUT_BURSTS) {
                return Decision(null, "Wide-zoom safety limit reached", cx, cy, scale, true)
            }
            zoomOutBursts += 1
            prepareForViewChange()
            nextActionAt = nowMs + ZOOM_COOLDOWN_MS
            return Decision(
                Command.Zoom(tele = false, durationMs = ZOOM_BURST_MS),
                "Gold clipped — zooming out…", cx, cy, scale, true
            )
        }

        if (!centered) {
            if (!gimbalReady) {
                return Decision(null, "Gold found — waiting for gimbal to steer", cx, cy, scale, true)
            }
            val choosePan = abs(dx) >= abs(dy)
            val duration = centeringDuration(if (choosePan) abs(dx) else abs(dy))
            if (choosePan) {
                val sign = if (dx > 0f) 1 else -1
                val candidate = panOffsetMs + sign * duration.toInt()
                if (abs(candidate) > GIMBAL_AXIS_BUDGET_MS) {
                    return Decision(null, "Pan safety limit reached", cx, cy, scale, true)
                }
                panOffsetMs = candidate
                prepareForViewChange()
                nextActionAt = nowMs + duration + GIMBAL_SETTLE_MS
                return Decision(Command.Pan(sign, duration), "Steering toward gold…", cx, cy, scale, true)
            }

            // Camera mount mapping confirmed live: axis1 above center looks
            // up, while image y grows down.
            val sign = if (dy > 0f) -1 else 1
            val candidate = tiltOffsetMs + sign * duration.toInt()
            if (abs(candidate) > GIMBAL_AXIS_BUDGET_MS) {
                return Decision(null, "Tilt safety limit reached", cx, cy, scale, true)
            }
            tiltOffsetMs = candidate
            prepareForViewChange()
            nextActionAt = nowMs + duration + GIMBAL_SETTLE_MS
            return Decision(Command.Tilt(sign, duration), "Steering toward gold…", cx, cy, scale, true)
        }

        if (centeredStreak < REQUIRED_CENTERED_FRAMES) {
            return Decision(null, "Gold centered — confirming…", cx, cy, scale, true)
        }
        if (focusConfirmFramesRemaining > 0) {
            return Decision(null, "Autofocus complete — measuring detail…", cx, cy, scale, true)
        }
        if (!focusConfirmed && !focusNeeded && sharpnessWindow.size >= SHARPNESS_WINDOW_SIZE) {
            focusConfirmed = sharpnessIsConfirmed()
            if (!focusConfirmed) focusNeeded = true
        }
        if (focusNeeded) {
            if (focusAttempts >= MAX_FOCUS_ATTEMPTS) {
                return Decision(null, "Focus not confirmed — check distance/light", cx, cy, scale, true)
            }
            focusAttempts += 1
            focusNeeded = false
            focusConfirmed = false
            focusConfirmFramesRemaining = FOCUS_CONFIRM_FRAMES
            sharpnessWindow.clear()
            nextActionAt = nowMs + FOCUS_HOLD_MS + FOCUS_SETTLE_MS
            return Decision(
                Command.Focus(FOCUS_HOLD_MS),
                "Gold centered — autofocus $focusAttempts/$MAX_FOCUS_ATTEMPTS…",
                cx, cy, scale, true
            )
        }
        if (!focusConfirmed) {
            return Decision(null, "Measuring focus…", cx, cy, scale, true)
        }
        if (scale < TARGET_MIN_SCALE) {
            if (zoomInBursts >= MAX_ZOOM_IN_BURSTS) {
                return Decision(null, "Tele-zoom safety limit reached", cx, cy, scale, true)
            }
            zoomInBursts += 1
            zoomOutBursts = 0
            prepareForViewChange()
            nextActionAt = nowMs + ZOOM_COOLDOWN_MS
            return Decision(
                Command.Zoom(tele = true, durationMs = ZOOM_BURST_MS),
                "Gold focused — zooming in…", cx, cy, scale, true
            )
        }
        return Decision(
            null,
            "Gold locked — focus confirmed (${formatSharpness()})",
            cx, cy, scale, true
        )
    }

    private fun prepareForViewChange() {
        detectionStreak = 0
        centeredStreak = 0
        lastObservationFrameId = -1L
        focusNeeded = true
        focusConfirmed = false
        focusAttempts = 0
        focusConfirmFramesRemaining = 0
        sharpnessWindow.clear()
    }

    private fun sharpnessIsConfirmed(): Boolean {
        if (sharpnessWindow.size < SHARPNESS_WINDOW_SIZE) return false
        val minSharpness = sharpnessWindow.minOrNull() ?: return false
        val maxSharpness = sharpnessWindow.maxOrNull() ?: return false
        val mean = sharpnessWindow.average().toFloat()
        if (mean < MIN_CONFIRMED_SHARPNESS) return false
        val relativeSpread = (maxSharpness - minSharpness) / mean.coerceAtLeast(0.000001f)
        return relativeSpread <= MAX_SHARPNESS_RELATIVE_SPREAD
    }

    private fun formatSharpness(): String =
        if (sharpnessWindow.isEmpty()) "sharp=—" else "sharp=%.4f".format(sharpnessWindow.average())

    private fun centeringDuration(error: Float): Long {
        val scaled = (error / 0.5f).coerceIn(0f, 1f)
        return (CENTER_MIN_MS + scaled * (CENTER_MAX_MS - CENTER_MIN_MS)).toLong()
    }

    companion object {
        private const val MIN_GOLD_POINTS = 6
        private const val REQUIRED_DETECTION_FRAMES = 3
        private const val REQUIRED_CENTERED_FRAMES = 3
        private const val LOSS_RESET_FRAMES = 5
        private const val EMA_ALPHA = 0.30f
        private const val CENTER_DEADBAND = 0.055f
        private const val TARGET_MIN_SCALE = 0.55f
        private const val MAX_TARGET_SCALE = 0.78f
        private const val EDGE_MARGIN = 0.025f
        private const val CENTER_MIN_MS = 200L
        private const val CENTER_MAX_MS = 520L
        private const val GIMBAL_SETTLE_MS = 450L
        private const val GIMBAL_AXIS_BUDGET_MS = 9_000
        private const val ZOOM_BURST_MS = 120L
        private const val ZOOM_COOLDOWN_MS = 750L
        private const val MAX_ZOOM_IN_BURSTS = 32
        private const val MAX_ZOOM_OUT_BURSTS = 12
        private const val FOCUS_HOLD_MS = 450L
        private const val FOCUS_SETTLE_MS = 500L
        private const val FOCUS_CONFIRM_FRAMES = 3
        private const val MAX_FOCUS_ATTEMPTS = 2
        private const val SHARPNESS_WINDOW_SIZE = 3
        private const val MIN_CONFIRMED_SHARPNESS = 0.0025f
        private const val MAX_SHARPNESS_RELATIVE_SPREAD = 0.45f
    }
}
