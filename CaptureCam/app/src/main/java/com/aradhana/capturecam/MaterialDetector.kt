package com.aradhana.capturecam

import androidx.camera.core.ImageProxy
import kotlin.math.max
import kotlin.math.min

/**
 * Port of static/capture_quality_worker.js's gold/silver blob detector --
 * same thresholds, same connected-component approach, same
 * "goldBoxArea" fallback for diamond-paved pieces (see the matching
 * comment in that file). Kept as a literal port rather than a rewrite so
 * the two stay behaviourally comparable if either needs tuning later.
 *
 * Runs directly on the YUV_420_888 frame CameraX hands ImageAnalysis --
 * sampled on a sparse grid (not every pixel) for real-time performance,
 * matching the web worker's own `step` stride sampling.
 */
object MaterialDetector {

    data class Bounds(val x0: Float, val y0: Float, val x1: Float, val y1: Float) {
        fun area(): Float = max(0f, x1 - x0) * max(0f, y1 - y0)
    }

    /** Normalized (0..1, against the raw analysis frame) point. */
    data class Point(val x: Float, val y: Float)

    data class Result(
        val material: Boolean,
        val bounds: Bounds?,
        val coverage: Float,
        val warmCoverage: Float,
        val goldRatio: Float,
        val goldBoxArea: Float,
        // Every sampled point classified as gold/silver/sparkle -- the
        // focus-peaking overlay draws a dot at each one instead of a single
        // box, so studs/diamonds/facets across the piece all light up
        // individually rather than just the metal's own bounding box.
        val points: List<Point> = emptyList()
    )

    private fun looksLikeGold(r: Int, g: Int, b: Int): Boolean {
        val maxV = max(r, max(g, b))
        val minV = min(r, min(g, b))
        val delta = maxV - minV
        val saturation = if (maxV != 0) delta.toFloat() / maxV else 0f
        val yLuma = 0.299f * r + 0.587f * g + 0.114f * b
        val cb = 128 - 0.168736f * r - 0.331264f * g + 0.5f * b
        val cr = 128 + 0.5f * r - 0.418688f * g - 0.081312f * b
        return yLuma > 35 && yLuma < 245 &&
            delta > 55 &&
            saturation > 0.34f &&
            r > 100 && g > 60 && b > 18 &&
            r - b >= 45 &&
            r - g >= 10 &&
            g - b >= 5 &&
            r >= g &&
            g >= b * 0.6 &&
            cr >= 138 && cr <= 210 &&
            cb >= 72 && cb <= 145
    }

    private fun looksLikeSilver(r: Int, g: Int, b: Int): Boolean {
        val maxV = max(r, max(g, b))
        val minV = min(r, min(g, b))
        val delta = maxV - minV
        val saturation = if (maxV != 0) delta.toFloat() / maxV else 0f
        val yLuma = 0.299f * r + 0.587f * g + 0.114f * b
        return yLuma > 70 && yLuma < 240 &&
            saturation < 0.14f &&
            delta < 30 &&
            maxV > 90
    }

    private fun looksLikeMetal(r: Int, g: Int, b: Int): Boolean =
        looksLikeGold(r, g, b) || looksLikeSilver(r, g, b)

    /** Diamonds/cut stones/studs read as bright, near-white specular
     * highlights -- the opposite signature deliberately excluded from
     * looksLikeSilver (which caps at yLuma<240 specifically to avoid
     * clipped-highlight false positives on real silver). Wanted here
     * anyway purely for the visual overlay -- this never feeds coverage/
     * material-detected, only the dot cloud. */
    private fun looksLikeSparkle(r: Int, g: Int, b: Int): Boolean {
        val maxV = max(r, max(g, b))
        val minV = min(r, min(g, b))
        val delta = maxV - minV
        val yLuma = 0.299f * r + 0.587f * g + 0.114f * b
        return yLuma >= 232 && delta < 45
    }

    /** Standard BT.601 YCbCr -> RGB, same conversion browsers already do
     * internally on camera frames before exposing RGBA pixel data -- close
     * enough to reuse the RGB-space thresholds above verbatim. */
    private fun yuvToRgb(y: Int, u: Int, v: Int): IntArray {
        val yy = y
        val uu = u - 128
        val vv = v - 128
        val r = (yy + 1.402f * vv).toInt().coerceIn(0, 255)
        val g = (yy - 0.344136f * uu - 0.714136f * vv).toInt().coerceIn(0, 255)
        val b = (yy + 1.772f * uu).toInt().coerceIn(0, 255)
        return intArrayOf(r, g, b)
    }

    /**
     * Analyses one frame. `step` controls sampling density in pixels
     * (higher = faster, coarser); the guide box restricts analysis to the
     * central region the operator is expected to frame the piece in,
     * matching the web worker's own guide-box restriction.
     */
    fun analyse(image: ImageProxy, step: Int = 6): Result {
        val width = image.width
        val height = image.height
        val yPlane = image.planes[0]
        val uPlane = image.planes[1]
        val vPlane = image.planes[2]
        val yBuffer = yPlane.buffer
        val uBuffer = uPlane.buffer
        val vBuffer = vPlane.buffer
        val yRowStride = yPlane.rowStride
        val uRowStride = uPlane.rowStride
        val uPixelStride = uPlane.pixelStride
        val vRowStride = vPlane.rowStride
        val vPixelStride = vPlane.pixelStride

        // Guide box: central 64% x 68% of frame, matching capture.html's
        // on-screen framing guide -- analysis outside it is noise (edges of
        // hand, background clutter at frame corners).
        val startX = (width * 0.18).toInt()
        val endX = (width * 0.82).toInt()
        val startY = (height * 0.16).toInt()
        val endY = (height * 0.84).toInt()

        val cols = max(1, (endX - startX) / step)
        val rows = max(1, (endY - startY) / step)
        val mask = BooleanArray(cols * rows)
        var warm = 0
        val points = mutableListOf<Point>()

        for (row in 0 until rows) {
            for (col in 0 until cols) {
                val x = min(width - 1, startX + col * step)
                val yPix = min(height - 1, startY + row * step)
                val yIndex = yPix * yRowStride + x
                if (yIndex < 0 || yIndex >= yBuffer.capacity()) continue
                val yVal = yBuffer.get(yIndex).toInt() and 0xFF
                val uvX = x / 2
                val uvY = yPix / 2
                val uIndex = uvY * uRowStride + uvX * uPixelStride
                val vIndex = uvY * vRowStride + uvX * vPixelStride
                if (uIndex < 0 || uIndex >= uBuffer.capacity() || vIndex < 0 || vIndex >= vBuffer.capacity()) continue
                val uVal = uBuffer.get(uIndex).toInt() and 0xFF
                val vVal = vBuffer.get(vIndex).toInt() and 0xFF
                val rgb = yuvToRgb(yVal, uVal, vVal)
                val isMetal = looksLikeMetal(rgb[0], rgb[1], rgb[2])
                if (isMetal) {
                    mask[row * cols + col] = true
                    warm += 1
                }
                if (isMetal || looksLikeSparkle(rgb[0], rgb[1], rgb[2])) {
                    points.add(Point(x.toFloat() / width, yPix.toFloat() / height))
                }
            }
        }

        if (warm == 0) return Result(false, null, 0f, 0f, 0f, 0f, points)

        // Connected-component largest blob (8-connectivity), same as
        // goldBlobDominance in the web worker.
        val visited = BooleanArray(mask.size)
        var bestSize = 0
        var bestMinCol = cols; var bestMinRow = rows; var bestMaxCol = -1; var bestMaxRow = -1
        val stack = ArrayDeque<Int>()
        for (start in mask.indices) {
            if (!mask[start] || visited[start]) continue
            var size = 0
            var minCol = cols; var minRow = rows; var maxCol = -1; var maxRow = -1
            stack.clear()
            stack.addLast(start)
            visited[start] = true
            while (stack.isNotEmpty()) {
                val current = stack.removeLast()
                size += 1
                val row = current / cols
                val col = current % cols
                if (col < minCol) minCol = col
                if (row < minRow) minRow = row
                if (col > maxCol) maxCol = col
                if (row > maxRow) maxRow = row
                for (dy in -1..1) for (dx in -1..1) {
                    if (dx == 0 && dy == 0) continue
                    val nr = row + dy
                    val nc = col + dx
                    if (nr < 0 || nc < 0 || nr >= rows || nc >= cols) continue
                    val next = nr * cols + nc
                    if (mask[next] && !visited[next]) {
                        visited[next] = true
                        stack.addLast(next)
                    }
                }
            }
            if (size > bestSize) {
                bestSize = size; bestMinCol = minCol; bestMinRow = minRow; bestMaxCol = maxCol; bestMaxRow = maxRow
            }
        }
        if (bestSize == 0) return Result(false, null, 0f, 0f, 0f, 0f)

        val bounds = Bounds(
            x0 = (startX + bestMinCol * step).toFloat() / width,
            y0 = (startY + bestMinRow * step).toFloat() / height,
            x1 = (startX + (bestMaxCol + 1) * step).toFloat() / width,
            y1 = (startY + (bestMaxRow + 1) * step).toFloat() / height
        )
        val warmCoverage = bestSize.toFloat() / mask.size
        val goldRatio = warm.toFloat() / mask.size
        val goldBoxArea = bounds.area()
        val goldDominant = warmCoverage >= 0.06f && (bestSize.toFloat() / warm) >= 0.40f
        val material = goldDominant || warmCoverage >= 0.012f || goldRatio >= 0.035f || goldBoxArea >= 0.05f

        return Result(
            material = material,
            bounds = bounds,
            coverage = goldBoxArea,
            warmCoverage = warmCoverage,
            goldRatio = goldRatio,
            goldBoxArea = goldBoxArea
        )
    }
}
