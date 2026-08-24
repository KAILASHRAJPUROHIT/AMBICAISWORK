package com.aradhana.capturecam

import android.graphics.Bitmap
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/**
 * Deterministic Sony Live View target selector. No ML/model/network input.
 *
 * MaterialDetector deliberately reports every broad warm-metal sample for
 * the phone capture UI. That is useful as focus peaking, but unsafe as a
 * physical steering target in a showroom: skin, wood, fabric, lamps and
 * reflections can all contain warm pixels. This selector tightens those
 * samples to yellow-gold hue, groups them into components, requires a dark
 * isolated surround plus metallic highlights, and acquires only inside the
 * central guide. Once acquired it follows the same component through a
 * wider area so small gimbal corrections and optical zoom can be measured.
 */
class SonyGoldTargetDetector {

    data class Target(
        val bounds: MaterialDetector.Bounds,
        val points: List<MaterialDetector.Point>,
        val scale: Float,
        val sharpness: Float,
        val darkSurroundFraction: Float,
        val highlightFraction: Float,
        val score: Float
    )

    data class Analysis(
        val target: Target?,
        val candidateCount: Int,
        val rawGoldPointCount: Int
    )

    private data class Component(
        val cells: List<Int>,
        val minCol: Int,
        val minRow: Int,
        val maxCol: Int,
        val maxRow: Int
    )

    private var lockedCenterX: Float? = null
    private var lockedCenterY: Float? = null
    private var lockLossFrames = 0
    private var pixelBuffer = IntArray(0)

    fun reset() {
        lockedCenterX = null
        lockedCenterY = null
        lockLossFrames = 0
    }

    fun analyse(bitmap: Bitmap): Analysis {
        val width = bitmap.width
        val height = bitmap.height
        if (width < 8 || height < 8) return Analysis(null, 0, 0)

        val broad = MaterialDetector.analyse(bitmap, step = SAMPLE_STEP, fullFrame = true)
        if (pixelBuffer.size < width * height) pixelBuffer = IntArray(width * height)
        val pixels = pixelBuffer
        bitmap.getPixels(pixels, 0, width, 0, 0, width, height)

        val cols = (width + SAMPLE_STEP - 1) / SAMPLE_STEP
        val rows = (height + SAMPLE_STEP - 1) / SAMPLE_STEP
        val mask = BooleanArray(cols * rows)
        var strictCount = 0
        for (point in broad.points) {
            val x = (point.x * width).toInt().coerceIn(0, width - 1)
            val y = (point.y * height).toInt().coerceIn(0, height - 1)
            if (!insideSearchArea(point.x, point.y)) continue
            if (!looksLikeStrictGold(pixels[y * width + x])) continue
            val col = (x / SAMPLE_STEP).coerceIn(0, cols - 1)
            val row = (y / SAMPLE_STEP).coerceIn(0, rows - 1)
            val index = row * cols + col
            if (!mask[index]) {
                mask[index] = true
                strictCount += 1
            }
        }
        if (strictCount == 0) return lost(0, broad.points.size)

        val components = connectedComponents(mask, cols, rows)
        val candidates = components.mapNotNull { component ->
            makeTarget(component, cols, width, height, pixels)
        }
        if (candidates.isEmpty()) return lost(0, broad.points.size)

        val lockX = lockedCenterX
        val lockY = lockedCenterY
        val eligible = candidates.filter { candidate ->
            val cx = (candidate.bounds.x0 + candidate.bounds.x1) / 2f
            val cy = (candidate.bounds.y0 + candidate.bounds.y1) / 2f
            if (lockX != null && lockY != null) {
                distance(cx, cy, lockX, lockY) <= LOCK_FOLLOW_DISTANCE
            } else {
                cx in ACQUIRE_LEFT..ACQUIRE_RIGHT && cy in ACQUIRE_TOP..ACQUIRE_BOTTOM
            }
        }
        if (eligible.isEmpty()) return lost(candidates.size, broad.points.size)

        val selected = eligible.maxByOrNull { candidate ->
            val cx = (candidate.bounds.x0 + candidate.bounds.x1) / 2f
            val cy = (candidate.bounds.y0 + candidate.bounds.y1) / 2f
            val continuity = if (lockX != null && lockY != null) {
                (1f - distance(cx, cy, lockX, lockY) / LOCK_FOLLOW_DISTANCE).coerceIn(0f, 1f) * 4f
            } else 0f
            candidate.score + continuity
        } ?: return lost(candidates.size, broad.points.size)

        lockedCenterX = (selected.bounds.x0 + selected.bounds.x1) / 2f
        lockedCenterY = (selected.bounds.y0 + selected.bounds.y1) / 2f
        lockLossFrames = 0
        return Analysis(selected, candidates.size, broad.points.size)
    }

    private fun lost(candidateCount: Int, rawPointCount: Int): Analysis {
        lockLossFrames += 1
        if (lockLossFrames >= LOCK_LOSS_RESET_FRAMES) reset()
        return Analysis(null, candidateCount, rawPointCount)
    }

    private fun makeTarget(
        component: Component,
        cols: Int,
        width: Int,
        height: Int,
        pixels: IntArray
    ): Target? {
        if (component.cells.size < MIN_COMPONENT_POINTS) return null
        val x0 = (component.minCol * SAMPLE_STEP).toFloat() / width
        val y0 = (component.minRow * SAMPLE_STEP).toFloat() / height
        val x1 = min(width, (component.maxCol + 1) * SAMPLE_STEP).toFloat() / width
        val y1 = min(height, (component.maxRow + 1) * SAMPLE_STEP).toFloat() / height
        val bounds = MaterialDetector.Bounds(x0, y0, x1, y1)
        val boxWidth = x1 - x0
        val boxHeight = y1 - y0
        val area = boxWidth * boxHeight
        val scale = max(boxWidth, boxHeight)
        val aspect = max(boxWidth, boxHeight) / max(0.0001f, min(boxWidth, boxHeight))
        if (area !in MIN_TARGET_AREA..MAX_TARGET_AREA ||
            scale !in MIN_TARGET_SCALE..MAX_TARGET_SCALE || aspect > MAX_ASPECT
        ) return null

        val boxCells = max(1, (component.maxCol - component.minCol + 1) *
            (component.maxRow - component.minRow + 1))
        val fill = component.cells.size.toFloat() / boxCells
        if (fill > MAX_COMPONENT_FILL) return null

        var highlights = 0
        val points = ArrayList<MaterialDetector.Point>(component.cells.size)
        for (cell in component.cells) {
            val row = cell / cols
            val col = cell % cols
            val x = min(width - 1, col * SAMPLE_STEP)
            val y = min(height - 1, row * SAMPLE_STEP)
            if (luma(pixels[y * width + x]) >= HIGHLIGHT_LUMA) highlights += 1
            points.add(MaterialDetector.Point(x.toFloat() / width, y.toFloat() / height, gold = true))
        }
        val highlightFraction = highlights.toFloat() / component.cells.size
        val darkSurround = darkSurroundFraction(bounds, width, height, pixels)
        if (darkSurround < MIN_DARK_SURROUND || highlightFraction < MIN_HIGHLIGHT_FRACTION) return null

        val sharpness = sharpness(bounds, width, height, pixels)
        val cx = (x0 + x1) / 2f
        val cy = (y0 + y1) / 2f
        val centerProximity = (1f - distance(cx, cy, 0.5f, 0.5f) / 0.707f).coerceIn(0f, 1f)
        val score = centerProximity * 3f + darkSurround * 2f +
            highlightFraction.coerceAtMost(0.4f) * 3f +
            min(2f, ln(1f + component.cells.size.toFloat()) * 0.35f) +
            min(1f, sharpness / SHARPNESS_REFERENCE)
        return Target(bounds, points, scale, sharpness, darkSurround, highlightFraction, score)
    }

    private fun connectedComponents(mask: BooleanArray, cols: Int, rows: Int): List<Component> {
        val visited = BooleanArray(mask.size)
        val stack = ArrayDeque<Int>()
        val result = ArrayList<Component>()
        for (start in mask.indices) {
            if (!mask[start] || visited[start]) continue
            val cells = ArrayList<Int>()
            var minCol = cols
            var minRow = rows
            var maxCol = -1
            var maxRow = -1
            visited[start] = true
            stack.addLast(start)
            while (stack.isNotEmpty()) {
                val current = stack.removeLast()
                cells.add(current)
                val row = current / cols
                val col = current % cols
                minCol = min(minCol, col)
                minRow = min(minRow, row)
                maxCol = max(maxCol, col)
                maxRow = max(maxRow, row)
                for (dy in -COMPONENT_GAP_CELLS..COMPONENT_GAP_CELLS) {
                    for (dx in -COMPONENT_GAP_CELLS..COMPONENT_GAP_CELLS) {
                        if (dx == 0 && dy == 0) continue
                        val nextRow = row + dy
                        val nextCol = col + dx
                        if (nextRow !in 0 until rows || nextCol !in 0 until cols) continue
                        val next = nextRow * cols + nextCol
                        if (mask[next] && !visited[next]) {
                            visited[next] = true
                            stack.addLast(next)
                        }
                    }
                }
            }
            result.add(Component(cells, minCol, minRow, maxCol, maxRow))
        }
        return result
    }

    private fun darkSurroundFraction(
        bounds: MaterialDetector.Bounds,
        width: Int,
        height: Int,
        pixels: IntArray
    ): Float {
        val padX = max(MIN_SURROUND_PAD, (bounds.x1 - bounds.x0) * 0.35f)
        val padY = max(MIN_SURROUND_PAD, (bounds.y1 - bounds.y0) * 0.35f)
        val outerX0 = ((bounds.x0 - padX).coerceAtLeast(0f) * width).toInt()
        val outerY0 = ((bounds.y0 - padY).coerceAtLeast(0f) * height).toInt()
        val outerX1 = ((bounds.x1 + padX).coerceAtMost(1f) * width).toInt()
        val outerY1 = ((bounds.y1 + padY).coerceAtMost(1f) * height).toInt()
        val innerX0 = (bounds.x0 * width).toInt()
        val innerY0 = (bounds.y0 * height).toInt()
        val innerX1 = (bounds.x1 * width).toInt()
        val innerY1 = (bounds.y1 * height).toInt()
        var dark = 0
        var samples = 0
        var y = outerY0
        while (y < outerY1) {
            var x = outerX0
            while (x < outerX1) {
                if (x !in innerX0 until innerX1 || y !in innerY0 until innerY1) {
                    samples += 1
                    if (luma(pixels[y.coerceIn(0, height - 1) * width + x.coerceIn(0, width - 1)]) < DARK_LUMA) {
                        dark += 1
                    }
                }
                x += SURROUND_SAMPLE_STEP
            }
            y += SURROUND_SAMPLE_STEP
        }
        return if (samples == 0) 0f else dark.toFloat() / samples
    }

    /** Normalized mean squared central-difference gradient in target ROI. */
    private fun sharpness(
        bounds: MaterialDetector.Bounds,
        width: Int,
        height: Int,
        pixels: IntArray
    ): Float {
        val x0 = max(1, (bounds.x0 * width).toInt())
        val y0 = max(1, (bounds.y0 * height).toInt())
        val x1 = min(width - 1, (bounds.x1 * width).toInt())
        val y1 = min(height - 1, (bounds.y1 * height).toInt())
        var sum = 0.0
        var count = 0
        var y = y0
        while (y < y1) {
            var x = x0
            while (x < x1) {
                val gx = luma(pixels[y * width + x + 1]) - luma(pixels[y * width + x - 1])
                val gy = luma(pixels[(y + 1) * width + x]) - luma(pixels[(y - 1) * width + x])
                sum += (gx * gx + gy * gy).toDouble()
                count += 1
                x += SHARPNESS_SAMPLE_STEP
            }
            y += SHARPNESS_SAMPLE_STEP
        }
        return if (count == 0) 0f else (sum / count / (2.0 * 255.0 * 255.0)).toFloat()
    }

    private fun looksLikeStrictGold(pixel: Int): Boolean {
        val r = pixel ushr 16 and 0xFF
        val g = pixel ushr 8 and 0xFF
        val b = pixel and 0xFF
        val maxV = max(r, max(g, b))
        val minV = min(r, min(g, b))
        val delta = maxV - minV
        if (maxV < 65 || maxV > 248 || delta == 0) return false
        val saturation = delta.toFloat() / maxV
        if (saturation < STRICT_MIN_SATURATION) return false
        val hue = when (maxV) {
            r -> 60f * ((g - b).toFloat() / delta).let { if (it < 0f) it + 6f else it }
            g -> 60f * ((b - r).toFloat() / delta + 2f)
            else -> 60f * ((r - g).toFloat() / delta + 4f)
        }
        return hue in STRICT_GOLD_HUE_MIN..STRICT_GOLD_HUE_MAX &&
            r >= g && g - b >= STRICT_GREEN_BLUE_GAP && r - b >= STRICT_RED_BLUE_GAP
    }

    private fun insideSearchArea(x: Float, y: Float): Boolean =
        x in SEARCH_LEFT..SEARCH_RIGHT && y in SEARCH_TOP..SEARCH_BOTTOM

    private fun luma(pixel: Int): Int {
        val r = pixel ushr 16 and 0xFF
        val g = pixel ushr 8 and 0xFF
        val b = pixel and 0xFF
        return (0.299f * r + 0.587f * g + 0.114f * b).toInt()
    }

    private fun distance(x0: Float, y0: Float, x1: Float, y1: Float): Float =
        sqrt((x0 - x1) * (x0 - x1) + (y0 - y1) * (y0 - y1))

    companion object {
        const val ACQUIRE_LEFT = 0.39f
        const val ACQUIRE_RIGHT = 0.61f
        const val ACQUIRE_TOP = 0.32f
        const val ACQUIRE_BOTTOM = 0.68f

        private const val SEARCH_LEFT = 0.10f
        private const val SEARCH_RIGHT = 0.90f
        private const val SEARCH_TOP = 0.08f
        private const val SEARCH_BOTTOM = 0.92f
        private const val SAMPLE_STEP = 5
        private const val COMPONENT_GAP_CELLS = 2
        private const val MIN_COMPONENT_POINTS = 6
        private const val MIN_TARGET_AREA = 0.00010f
        private const val MAX_TARGET_AREA = 0.12f
        private const val MIN_TARGET_SCALE = 0.015f
        private const val MAX_TARGET_SCALE = 0.48f
        private const val MAX_ASPECT = 5.0f
        private const val MAX_COMPONENT_FILL = 0.62f
        private const val STRICT_MIN_SATURATION = 0.35f
        private const val STRICT_GOLD_HUE_MIN = 32f
        private const val STRICT_GOLD_HUE_MAX = 68f
        private const val STRICT_GREEN_BLUE_GAP = 18
        private const val STRICT_RED_BLUE_GAP = 48
        private const val HIGHLIGHT_LUMA = 175
        private const val MIN_HIGHLIGHT_FRACTION = 0.025f
        private const val DARK_LUMA = 72
        private const val MIN_DARK_SURROUND = 0.30f
        private const val MIN_SURROUND_PAD = 0.018f
        private const val SURROUND_SAMPLE_STEP = 4
        private const val SHARPNESS_SAMPLE_STEP = 2
        private const val SHARPNESS_REFERENCE = 0.012f
        private const val LOCK_FOLLOW_DISTANCE = 0.22f
        private const val LOCK_LOSS_RESET_FRAMES = 8
    }
}
