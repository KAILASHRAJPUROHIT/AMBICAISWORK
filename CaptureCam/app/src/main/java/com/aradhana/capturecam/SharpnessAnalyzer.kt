package com.aradhana.capturecam

import android.graphics.Bitmap
import androidx.camera.core.ImageProxy
import kotlin.math.max
import kotlin.math.min

/**
 * Laplacian-variance sharpness, computed directly on the Y (luma) plane
 * inside the detected material bounds. This is deliberately a SECONDARY
 * signal here, not the primary one -- unlike the browser version (which had
 * no choice but to infer focus from blur heuristics), this app gets the
 * real answer from Camera2's CONTROL_AF_STATE (see FocusController.kt).
 * This exists as a final sanity cross-check right before the shutter
 * fires: AF can report FOCUSED_LOCKED and the frame can still have gone
 * soft in the few hundred ms since (subject bumped, hand moved).
 */
object SharpnessAnalyzer {

    /** Returns a 0..100-ish score; higher is sharper. Not calibrated to
     * match the web worker's scale, only used as this app's own threshold. */
    fun score(image: ImageProxy, bounds: MaterialDetector.Bounds, step: Int = 3): Float {
        val width = image.width
        val height = image.height
        val yPlane = image.planes[0]
        val yBuffer = yPlane.buffer
        val rowStride = yPlane.rowStride

        val x0 = max(1, (bounds.x0 * width).toInt())
        val x1 = min(width - 2, (bounds.x1 * width).toInt())
        val y0 = max(1, (bounds.y0 * height).toInt())
        val y1 = min(height - 2, (bounds.y1 * height).toInt())
        if (x1 - x0 < 6 || y1 - y0 < 6) return 0f

        fun luma(x: Int, y: Int): Int {
            val idx = y * rowStride + x
            return if (idx in 0 until yBuffer.capacity()) yBuffer.get(idx).toInt() and 0xFF else 0
        }

        var sum = 0.0
        var sumSquares = 0.0
        var count = 0
        var y = y0
        while (y < y1) {
            var x = x0
            while (x < x1) {
                val lap = 4 * luma(x, y) - luma(x - 1, y) - luma(x + 1, y) - luma(x, y - 1) - luma(x, y + 1)
                sum += lap
                sumSquares += lap.toDouble() * lap
                count += 1
                x += step
            }
            y += step
        }
        if (count == 0) return 0f
        val mean = sum / count
        val variance = max(0.0, sumSquares / count - mean * mean)
        // Empirically-scaled to land roughly in a 0..100 range for typical
        // in-focus jewellery close-ups; tuned against the same style of
        // shots the web worker's CAPTURE_SHARP thresholds were tuned on.
        return ((variance - 20.0) / 170.0 * 100.0).coerceIn(0.0, 100.0).toFloat()
    }

    /**
     * Raw (unnormalized) Laplacian variance over the actual captured
     * full-resolution bitmap -- deliberately NOT mapped onto [score]'s 0..100
     * scale, because that scale was tuned against the low-res ImageAnalysis
     * stream (a fraction of the sensor's native resolution). A frame can
     * read as "sharp enough" on that downsampled live stream while still
     * showing real blur once viewed at full resolution, since the
     * downsample itself throws away the fine detail that would reveal it.
     * This exists purely to measure sharpness against the actual delivered
     * pixels, not to replace the live gate. Not yet given a pass/fail
     * threshold in code -- the raw variance scale needs one real capture's
     * numbers (logged by the caller) before a cutoff can be picked with any
     * confidence, rather than guessed blind.
     */
    fun scoreBitmapRaw(bitmap: Bitmap, step: Int = 6): Double {
        val width = bitmap.width
        val height = bitmap.height
        if (width < 8 || height < 8) return 0.0

        fun luma(x: Int, y: Int): Int {
            val p = bitmap.getPixel(x, y)
            val r = (p shr 16) and 0xFF
            val g = (p shr 8) and 0xFF
            val b = p and 0xFF
            return (r * 299 + g * 587 + b * 114) / 1000
        }

        var sum = 0.0
        var sumSquares = 0.0
        var count = 0
        var y = 1
        while (y < height - 1) {
            var x = 1
            while (x < width - 1) {
                val lap = 4 * luma(x, y) - luma(x - 1, y) - luma(x + 1, y) - luma(x, y - 1) - luma(x, y + 1)
                sum += lap
                sumSquares += lap.toDouble() * lap
                count += 1
                x += step
            }
            y += step
        }
        if (count == 0) return 0.0
        val mean = sum / count
        return max(0.0, sumSquares / count - mean * mean)
    }
}
