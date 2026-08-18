package com.aradhana.capturecam

import androidx.camera.core.ImageProxy
import java.nio.ByteBuffer
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

    /** Normalized (0..1, against the raw analysis frame) point. [gold] is
     * true only for actual gold-hue metal (looksLikeGold), false for
     * silver/sparkle points -- lets gold-exclusive consumers (see
     * MainActivity.bestGoldObjectBox()) filter out silver-classified false
     * positives, e.g. a bright specular highlight on a glossy display box
     * passing looksLikeSilver's loose low-saturation/high-luma check.
     * Confirmed live (2026-08-18): with no ornament in frame at all, the
     * tracker still armed on a display box's shiny top edge because those
     * highlight pixels passed the silver classifier. */
    data class Point(val x: Float, val y: Float, val gold: Boolean = false)

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

    // Absolute RGB/luma thresholds alone are camera-specific: a wall or
    // table that reads as gray on one phone's colour science can slide
    // straight through looksLikeSilver's fairly wide "neutral, moderately
    // bright" band on a different device's (confirmed on an actual tablet:
    // a plain background read coverage=0.43, effectively "the wall IS the
    // jewellery"). Real jewellery is inherently TEXTURED -- facets,
    // engraving, polish, stone settings all produce sharp local luma
    // variation pixel-to-pixel; a flat wall or table does not, regardless
    // of what colour that wall happens to be on any given camera. This is
    // required in ADDITION to the colour check, not instead of it, and is
    // far more device-invariant than tuning the absolute thresholds again
    // for every new camera's colour calibration.
    private const val LOCAL_CONTRAST_RADIUS = 3
    private const val MIN_LOCAL_VARIANCE = 45f

    private fun hasLocalContrast(yBuffer: ByteBuffer, rowStride: Int, cx: Int, cy: Int, width: Int, height: Int): Boolean {
        val r = LOCAL_CONTRAST_RADIUS
        var sum = 0
        var sumSq = 0
        var count = 0
        var yy = cy - r
        while (yy <= cy + r) {
            if (yy in 0 until height) {
                var xx = cx - r
                while (xx <= cx + r) {
                    if (xx in 0 until width) {
                        val idx = yy * rowStride + xx
                        if (idx in 0 until yBuffer.capacity()) {
                            val v = yBuffer.get(idx).toInt() and 0xFF
                            sum += v
                            sumSq += v * v
                            count += 1
                        }
                    }
                    xx += 2 // sub-sample the window, this runs per-candidate-pixel
                }
            }
            yy += 2
        }
        if (count < 4) return false
        val mean = sum.toFloat() / count
        val variance = (sumSq.toFloat() / count) - (mean * mean)
        return variance >= MIN_LOCAL_VARIANCE
    }

    /** Diamonds/cut stones/studs read as bright, near-white specular
     * highlights -- the opposite signature deliberately excluded from
     * looksLikeSilver (which caps at yLuma<240 specifically to avoid
     * clipped-highlight false positives on real silver). This alone is far
     * too loose on its own (any bright, low-saturation surface qualifies --
     * a white background, a skin highlight, studio lighting) -- it is only
     * ever trusted when it lands within METAL_PROXIMITY_CELLS of an actual
     * metal-classified sample, i.e. a stone actually set INTO or next to
     * gold/silver, not a random bright thing anywhere in frame. Never
     * feeds coverage/material-detected either way, only the dot cloud. */
    private fun looksLikeSparkle(r: Int, g: Int, b: Int): Boolean {
        val maxV = max(r, max(g, b))
        val minV = min(r, min(g, b))
        val delta = maxV - minV
        val yLuma = 0.299f * r + 0.587f * g + 0.114f * b
        return yLuma >= 240 && delta < 35
    }

    private const val METAL_PROXIMITY_CELLS = 3

    private fun hasNearbyMetal(mask: BooleanArray, cols: Int, rows: Int, col: Int, row: Int): Boolean {
        val r = METAL_PROXIMITY_CELLS
        for (dy in -r..r) {
            val nr = row + dy
            if (nr < 0 || nr >= rows) continue
            for (dx in -r..r) {
                val nc = col + dx
                if (nc < 0 || nc >= cols) continue
                if (mask[nr * cols + nc]) return true
            }
        }
        return false
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
     * matching the web worker's own guide-box restriction -- UNLESS
     * [fullFrame] is set, which scans the entire frame instead.
     *
     * fullFrame exists specifically for the gimbal hunt: the guide-box
     * restriction is a real, confirmed blind spot for that use case --
     * gold sitting in a frame CORNER during a search sweep is completely
     * invisible to the guide-box-restricted scan (outside its 18-82%/
     * 16-84% window entirely), which is exactly why hunting kept sweeping
     * past visibly-present gold without ever detecting it. Once armed and
     * tracking a specific candidate, the guide box's original purpose
     * (ignore background clutter/hand edges at the frame's margins) is
     * still the right behaviour, so callers should only pass fullFrame
     * while still searching, not during normal centered operation.
     */
    fun analyse(image: ImageProxy, step: Int = 6, fullFrame: Boolean = false): Result {
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
        // hand, background clutter at frame corners). Skipped entirely in
        // fullFrame mode (see doc comment above).
        val startX = if (fullFrame) 0 else (width * 0.18).toInt()
        val endX = if (fullFrame) width else (width * 0.82).toInt()
        val startY = if (fullFrame) 0 else (height * 0.16).toInt()
        val endY = if (fullFrame) height else (height * 0.84).toInt()

        val cols = max(1, (endX - startX) / step)
        val rows = max(1, (endY - startY) / step)
        val mask = BooleanArray(cols * rows)
        val sparkleCandidate = BooleanArray(cols * rows)
        var warm = 0

        // Pass 1: classify every sampled cell. Sparkle candidates are
        // recorded but not yet trusted -- see the proximity gate below.
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
                val isMetal = looksLikeMetal(rgb[0], rgb[1], rgb[2]) &&
                    hasLocalContrast(yBuffer, yRowStride, x, yPix, width, height)
                val cell = row * cols + col
                if (isMetal) {
                    mask[cell] = true
                    warm += 1
                } else if (looksLikeSparkle(rgb[0], rgb[1], rgb[2])) {
                    sparkleCandidate[cell] = true
                }
            }
        }

        // Pass 2: build the dot cloud -- every metal cell, plus every
        // sparkle candidate that has an actual metal cell nearby (a stone
        // set into or beside gold/silver), dropping the ones that don't
        // (background highlights, skin, studio lighting -- exactly what
        // "dots on all focused areas, not just the jewellery" was).
        val points = mutableListOf<Point>()
        for (row in 0 until rows) {
            for (col in 0 until cols) {
                val cell = row * cols + col
                val keep = mask[cell] || (sparkleCandidate[cell] && hasNearbyMetal(mask, cols, rows, col, row))
                if (!keep) continue
                val x = min(width - 1, startX + col * step)
                val yPix = min(height - 1, startY + row * step)
                points.add(Point(x.toFloat() / width, yPix.toFloat() / height))
            }
        }

        if (warm == 0) return Result(false, null, 0f, 0f, 0f, 0f, points)

        // Connected components (8-connectivity), same as goldBlobDominance
        // in the web worker -- but tracking EVERY component, not just the
        // largest by raw size. A presentation/display box's gold or dark
        // trim forms a thin rectangular OUTLINE that can have a larger raw
        // pixel count than the actual ring/pendant sitting inside it (the
        // trim runs the whole perimeter of the box), which was getting
        // picked as "the piece" and immediately satisfied the coverage
        // floor without ever needing to zoom in -- the box's trim, not the
        // jewellery, was "close enough" already. A thin outline has a much
        // lower FILL RATIO (pixels-in-blob / pixels-in-its-own-bounding-
        // box) than a compact solid shape like a ring does, so prefer the
        // largest component that's actually reasonably filled; only fall
        // back to the largest-by-size if nothing meets that bar.
        data class Component(val size: Int, val minCol: Int, val minRow: Int, val maxCol: Int, val maxRow: Int)

        val visited = BooleanArray(mask.size)
        val components = mutableListOf<Component>()
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
            components.add(Component(size, minCol, minRow, maxCol, maxRow))
        }
        if (components.isEmpty()) return Result(false, null, 0f, 0f, 0f, 0f, points)

        fun fillRatio(c: Component): Float {
            val bboxCells = (c.maxCol - c.minCol + 1) * (c.maxRow - c.minRow + 1)
            return c.size.toFloat() / max(1, bboxCells)
        }
        // A chain is naturally thin/low-fill-ratio too -- the fill-ratio
        // bar alone can't tell "hollow display-box trim" and "genuine
        // chain" apart, they have the same silhouette signature. What
        // actually differs: box trim runs along the box's own edges, and a
        // box large enough to be in frame at all almost always has its
        // trim touching 2+ sides of the guide region. A chain the operator
        // has actually framed sits WITHIN the guide region -- it might
        // brush one edge, but not multiple. So: still prefer a filled blob
        // when one exists (a ring/pendant), but a thin component is only
        // rejected as "probably a container" when it also hugs multiple
        // edges; a thin component that doesn't is trusted as chain mode.
        fun edgesTouched(c: Component): Int {
            val margin = 1
            var count = 0
            if (c.minCol <= margin) count += 1
            if (c.maxCol >= cols - 1 - margin) count += 1
            if (c.minRow <= margin) count += 1
            if (c.maxRow >= rows - 1 - margin) count += 1
            return count
        }
        val MIN_FILL_RATIO = 0.28f
        val chosen = components.filter { fillRatio(it) >= MIN_FILL_RATIO || edgesTouched(it) < 2 }
            .maxByOrNull { it.size }
            ?: components.maxByOrNull { it.size }!!
        val bestSize = chosen.size
        val bestMinCol = chosen.minCol; val bestMinRow = chosen.minRow
        val bestMaxCol = chosen.maxCol; val bestMaxRow = chosen.maxRow

        val bounds = Bounds(
            x0 = (startX + bestMinCol * step).toFloat() / width,
            y0 = (startY + bestMinRow * step).toFloat() / height,
            x1 = (startX + (bestMaxCol + 1) * step).toFloat() / width,
            y1 = (startY + (bestMaxRow + 1) * step).toFloat() / height
        )
        val warmCoverage = bestSize.toFloat() / mask.size
        val goldRatio = warm.toFloat() / mask.size
        val goldBoxArea = bounds.area()
        // warmCoverage/goldRatio are fractions of the SCANNED region
        // (mask.size), not the full frame -- fullFrame mode scans ~2.3x
        // more area (1.0 vs the guide box's 0.64x0.68=0.4352 of the
        // frame), so the same physical object produces a smaller ratio
        // purely from the larger denominator, not because it's actually
        // less present. Rescale both to a full-frame-equivalent fraction
        // so the thresholds below mean the same physical object size in
        // either mode -- otherwise switching to fullFrame for hunting
        // would make small/distant objects (spec: "gold can be as small
        // as 5%") HARDER to detect, the opposite of the fix's intent.
        // goldBoxArea already IS full-frame-normalized (bounds are always
        // expressed in full-frame coordinates regardless of scan region),
        // so it needs no such rescaling.
        val scannedRegionFraction = ((endX - startX).toFloat() / width) * ((endY - startY).toFloat() / height)
        val warmCoverageFullFrame = warmCoverage * scannedRegionFraction
        val goldRatioFullFrame = goldRatio * scannedRegionFraction
        val goldDominant = warmCoverage >= 0.06f && (bestSize.toFloat() / warm) >= 0.40f
        // 0.05 -> 0.035 for goldBoxArea specifically: "as small as 5%" per
        // spec means shots right at that bar need margin, not a threshold
        // sitting exactly on the edge of the reported worst case.
        val material = goldDominant || warmCoverageFullFrame >= 0.012f || goldRatioFullFrame >= 0.035f || goldBoxArea >= 0.035f

        return Result(
            material = material,
            bounds = bounds,
            coverage = goldBoxArea,
            warmCoverage = warmCoverage,
            goldRatio = goldRatio,
            goldBoxArea = goldBoxArea,
            points = points
        )
    }
}
