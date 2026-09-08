package com.aradhana.capturecam

import android.graphics.Bitmap
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

    // Sony Live View arrives as JPEG -> Bitmap rather than CameraX's
    // YUV_420_888 ImageProxy. Reuse one ARGB readback buffer so the
    // continuous preview does not allocate a multi-megabyte IntArray on
    // every frame. The Bitmap overload below is synchronized because this
    // singleton owns that reusable buffer.
    private var bitmapArgbBuffer = IntArray(0)

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
        val points: List<Point> = emptyList(),
        // Fraction of GOLD-classified samples that are blown out (luma
        // near max) -- see looksLikeGold's yLuma<245 ceiling, this counts
        // slightly under that so it catches "about to clip" too. Feeds
        // MainActivity's auto-exposure logic (2026-08-18): a real, if
        // coarse, per-frame signal for "reflections are eating design
        // detail right now" without any extra image analysis pass --
        // reuses the same YUV sampling loop that already runs for gold
        // detection.
        val highlightClipFraction: Float = 0f,
        // Fraction of ALL sampled cells (any classification, not just gold)
        // that are blown out. Confirmed live (2026-08-18): the owner
        // reported every capture coming out overexposed while
        // highlightClipFraction kept reading 0.0 nearly every tick -- the
        // gold studs themselves weren't clipping, but the surrounding
        // scene/background was, and gold-only clipping has zero visibility
        // into that. This is the scene-wide signal applyAutoExposure()
        // needed but didn't have.
        val sceneClipFraction: Float = 0f,
        // Small gold blobs sitting in the lower portion of the piece's own
        // bounds -- candidate ghungroo/dangler beads, for the left/right
        // symmetry check (2026-08-19, explicit request: staff flagged that
        // a bent-under or hidden ghungroo is easy to miss by eye through
        // the phone screen during capture). Deliberately loose (any small
        // low-hanging blob, not a verified bead shape) since this only
        // feeds an advisory count-mismatch warning, never a capture gate.
        val danglerBlobs: List<Bounds> = emptyList()
    )

    /** True if the detected material's bounding box touches (or nearly
     * touches) any of the four frame edges -- the ornament is bigger than
     * what the frame can currently show, not merely well-framed. Distinct
     * from highlightClipFraction/sceneClipFraction (those measure
     * BRIGHTNESS clipping on gold/scene pixels, not spatial framing).
     * Confirmed live (2026-08-19) on a bracelet at 3.4x zoom during the
     * LEFT ANGLE step: goldClip=0.000, sceneClip=0.029 (no exposure
     * problem at all) while the tracked band ran edge-to-edge left-right
     * and the bracelet's own curve continued past top/bottom -- nothing
     * caught it before READY lit up, because neither clip metric nor
     * waitForStableFrame's presence/focus/sharpness gate looks at whether
     * the object's own box is spilling off the visible frame. `bounds` is
     * already normalized 0..1 against the analysis frame (see Point's doc
     * comment above), so this needs no new pixel sampling. */
    fun touchesFrameEdge(bounds: Bounds?, margin: Float = 0.015f): Boolean {
        if (bounds == null) return false
        return bounds.x0 <= margin || bounds.y0 <= margin ||
            bounds.x1 >= 1f - margin || bounds.y1 >= 1f - margin
    }

    /** Rough live guess at "does this piece have a diamond/rhodium stud
     * accent" (2026-08-19, explicit request) -- reuses the sparkle-near-
     * metal points [analyse] already builds for the focus-peaking overlay
     * (Point.gold=false marks them), no new pixel analysis. Deliberately
     * approximate: a small, scattered non-gold cluster reads as a likely
     * stone/stud accent; a near-zero or near-total non-gold fraction reads
     * as "no accent" or "broadly silver-toned metal" respectively, neither
     * of which is a stud. This is advisory ONLY -- explicitly a starting
     * guess the operator confirms or corrects in the live preview
     * (MainActivity.studStatusText), never a capture gate. False positives
     * are expected (a blown-out gold specular highlight also reads as
     * "sparkle near metal", the same ambiguity found live 2026-08-19 on
     * GR22/127's ring engraving) -- that is exactly why the UI needs a
     * one-tap correction rather than trusting this outright. */
    fun studCandidate(points: List<Point>): Boolean {
        val total = points.size
        if (total < 20) return false
        val nonGold = points.count { !it.gold }
        val frac = nonGold.toFloat() / total
        return nonGold >= 5 && frac in 0.02f..0.35f
    }

    /** Illumination-invariant chromaticity approach (2026-08-29 fix,
     * research-backed): the previous version gated on absolute channel
     * values/differences (r > 100, delta > 55, r-b >= 45, etc.), which all
     * shrink toward zero as a pixel darkens -- a genuinely gold pixel in
     * shadow (same hue, lower brightness) failed these floors even though
     * every ratio/hue signal still matched. Live-confirmed: a chain's
     * segment nearest the ring light classified as gold; the same chain a
     * few inches into shadow did not, despite being visually identical
     * gold to the eye. The standard CV fix (illumination-invariant colour
     * recognition via channel-normalized chromaticity) is to classify on
     * RATIOS between channels, not their absolute magnitude, since a dim
     * gold pixel keeps the same r:g:b proportion as a bright one. delta/
     * saturation/cr/cb were already ratio-like and are kept; the absolute
     * floors and differences are replaced with channel ratios so darker
     * gold now passes while grey/near-neutral backdrop and stand
     * (r≈g≈b, ratios ≈1.0) still correctly fails. yLuma/saturation floors
     * are lowered, not removed -- still excludes true near-black noise and
     * near-grey surfaces, just no longer double-penalizes darkness on top
     * of the ratio checks doing the real hue discrimination. */
    private fun looksLikeGold(r: Int, g: Int, b: Int): Boolean {
        val maxV = max(r, max(g, b))
        val minV = min(r, min(g, b))
        val delta = maxV - minV
        val saturation = if (maxV != 0) delta.toFloat() / maxV else 0f
        val yLuma = 0.299f * r + 0.587f * g + 0.114f * b
        val cb = 128 - 0.168736f * r - 0.331264f * g + 0.5f * b
        val cr = 128 + 0.5f * r - 0.418688f * g - 0.081312f * b
        val safeB = max(b, 1).toFloat()
        val safeG = max(g, 1).toFloat()
        return yLuma > 18 && yLuma < 245 &&
            saturation > 0.22f &&
            r >= g && g >= b &&
            r / safeB >= 1.7f &&
            r / safeG >= 1.08f &&
            g / safeB >= 1.3f &&
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
        val goldMask = BooleanArray(cols * rows)
        val sparkleCandidate = BooleanArray(cols * rows)
        var warm = 0
        var goldSampleCount = 0
        var goldClippedCount = 0
        var sampleCount = 0
        var sceneClippedCount = 0

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
                sampleCount += 1
                // 240 (near-pure white) was too strict -- confirmed live
                // (2026-08-18) with a demonstrably working exposure control
                // (verified via a direct EV override) that never engaged
                // automatically, because a washed-out grey studio background
                // reads more like a flat, moderately bright grey (never
                // actually hitting true sensor saturation) than it does
                // pure white. 200 catches "this looks overexposed to a
                // human" rather than only literal clipping.
                if (yVal >= 200) sceneClippedCount += 1
                val isMetal = looksLikeMetal(rgb[0], rgb[1], rgb[2]) &&
                    hasLocalContrast(yBuffer, yRowStride, x, yPix, width, height)
                val cell = row * cols + col
                if (isMetal) {
                    mask[cell] = true
                    if (looksLikeGold(rgb[0], rgb[1], rgb[2])) {
                        goldMask[cell] = true
                        goldSampleCount += 1
                        if (yVal >= 240) goldClippedCount += 1
                    }
                    warm += 1
                } else if (looksLikeSparkle(rgb[0], rgb[1], rgb[2])) {
                    sparkleCandidate[cell] = true
                }
            }
        }
        val highlightClipFraction = if (goldSampleCount > 0) goldClippedCount.toFloat() / goldSampleCount else 0f
        val sceneClipFraction = if (sampleCount > 0) sceneClippedCount.toFloat() / sampleCount else 0f

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
                points.add(Point(x.toFloat() / width, yPix.toFloat() / height, gold = goldMask[cell]))
            }
        }

        if (warm == 0) return Result(false, null, 0f, 0f, 0f, 0f, points, highlightClipFraction, sceneClipFraction)

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

        // Gold-only connectivity: this blob selection is what becomes
        // result.bounds, which drives tracking/centering/zoom-climb whenever
        // ML Kit's box isn't available (ML_KIT_OBJECT_DETECTION_ENABLED is
        // currently false, so this is the ONLY box in play right now).
        // Walking `mask` (gold OR silver, via looksLikeMetal) let a large,
        // well-filled SILVER-classified blob -- e.g. a wet/dimpled steel
        // stand, whose dimples give it plenty of real local contrast so
        // hasLocalContrast's flat-surface guard doesn't catch it -- win the
        // largest-reasonably-filled-component pick outright and pull bounds
        // (and therefore the gimbal/zoom) onto it instead of the actual gold
        // piece. Confirmed live (2026-08-18): tracker zoomed in on a
        // stainless surface next to a pair of gold tops. bestGoldObjectBox()
        // already restricts to gold-only points + a spatial-continuity
        // anchor for the ML-Kit path per the standing "focus on gold only,
        // always" rule -- this walk over goldMask brings the colour-only
        // fallback path (the one actually active right now) in line with
        // that same rule, so a silver/steel blob can never be selected here
        // at all, regardless of size or fill ratio.
        val visited = BooleanArray(goldMask.size)
        val components = mutableListOf<Component>()
        val stack = ArrayDeque<Int>()
        for (start in goldMask.indices) {
            if (!goldMask[start] || visited[start]) continue
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
                    if (goldMask[next] && !visited[next]) {
                        visited[next] = true
                        stack.addLast(next)
                    }
                }
            }
            components.add(Component(size, minCol, minRow, maxCol, maxRow))
        }
        if (components.isEmpty()) return Result(false, null, 0f, 0f, 0f, 0f, points, highlightClipFraction, sceneClipFraction)

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
        val real = components.filter { fillRatio(it) >= MIN_FILL_RATIO || edgesTouched(it) < 2 }
        val primary = real.maxByOrNull { it.size } ?: components.maxByOrNull { it.size }!!
        // Pair jewellery (two stud earrings on one stand, a pair of bangles,
        // etc.) is two physically separate gold blobs -- picking only the
        // single largest one made zoom climb to fill 75% of frame with ONE
        // earring, cropping its twin out entirely. Confirmed live
        // (2026-08-18): both tops correctly detected (gold-only dots on
        // each), but bounds locked onto one and zoomed straight past the
        // other. Union in any OTHER real component that's a comparably
        // sized piece (not a stray noise speck) so the pair frames
        // together -- 25% of the primary's size is generous enough for two
        // genuinely different-sized real pieces (e.g. a pendant + a smaller
        // chain clasp) but excludes a tiny few-pixel false positive.
        val PAIR_SIZE_RATIO = 0.25f
        var bestMinCol = primary.minCol; var bestMinRow = primary.minRow
        var bestMaxCol = primary.maxCol; var bestMaxRow = primary.maxRow
        var bestSize = primary.size
        for (c in real) {
            if (c === primary) continue
            if (c.size < primary.size * PAIR_SIZE_RATIO) continue
            bestMinCol = min(bestMinCol, c.minCol); bestMinRow = min(bestMinRow, c.minRow)
            bestMaxCol = max(bestMaxCol, c.maxCol); bestMaxRow = max(bestMaxRow, c.maxRow)
            bestSize += c.size
        }
        // Chain-strap extension (2026-08-28, live-confirmed on a necklace):
        // a chain's thin straps sample as several SMALL disconnected
        // components (the `step` stride skips over gaps in a thin line),
        // each individually far below PAIR_SIZE_RATIO of the dense
        // pendant/bead cluster that becomes `primary` -- so the pair-union
        // above never picks them up, and `bounds` locks onto just the
        // dense center, cropping the visible straps out entirely (a real
        // capture showed exactly this: box on the pendant beads only, the
        // chain running to both frame edges outside it). Distinct problem
        // from the pair-union: not "two similarly-sized pieces", but "many
        // small pieces that physically continue the primary blob outward".
        // Chains in any real component whose bounding box is within a
        // small gap of the union SO FAR -- iterated, since a strap segment
        // two hops out only becomes "close" once the first hop is already
        // unioned in. Capped iteration count is just a safety backstop
        // (there are only ever a handful of real components per frame);
        // it is not expected to bind in practice.
        //
        // Tolerance scales with the union box's OWN current span, not a
        // flat frame fraction (a flat 5%-of-frame tolerance still cropped
        // the top connector tabs on a real capture): a necklace already
        // known to be large should get proportionally more reach to keep
        // continuing itself (the last gap to a small, sparse connector tab
        // can be wider than 5% of the whole frame on a piece this size),
        // while a small ring's stray fleck still gets almost none, since
        // 15% of a tiny union box is itself tiny. Recomputed every pass
        // since the union box grows. minimumTolerance is the floor for a
        // still-small union early in the chain.
        val minimumTolerance = (0.05f * max(cols, rows)).toInt().coerceAtLeast(2)
        var grew = true
        var guard = 0
        while (grew && guard < 8) {
            grew = false
            guard += 1
            val unionSpan = max(bestMaxCol - bestMinCol, bestMaxRow - bestMinRow)
            val gapTolerance = max(minimumTolerance, (0.18f * unionSpan).toInt())
            for (c in real) {
                if (c === primary) continue
                if (c.minCol >= bestMinCol && c.maxCol <= bestMaxCol &&
                    c.minRow >= bestMinRow && c.maxRow <= bestMaxRow
                ) continue // already inside the union box
                val colGap = max(0, max(bestMinCol - c.maxCol, c.minCol - bestMaxCol))
                val rowGap = max(0, max(bestMinRow - c.maxRow, c.minRow - bestMaxRow))
                if (colGap > gapTolerance || rowGap > gapTolerance) continue
                bestMinCol = min(bestMinCol, c.minCol); bestMinRow = min(bestMinRow, c.minRow)
                bestMaxCol = max(bestMaxCol, c.maxCol); bestMaxRow = max(bestMaxRow, c.maxRow)
                bestSize += c.size
                grew = true
            }
        }

        val bounds = Bounds(
            x0 = (startX + bestMinCol * step).toFloat() / width,
            y0 = (startY + bestMinRow * step).toFloat() / height,
            x1 = (startX + (bestMaxCol + 1) * step).toFloat() / width,
            y1 = (startY + (bestMaxRow + 1) * step).toFloat() / height
        )
        if (guard > 1) {
            android.util.Log.d(
                "MaterialDetector",
                "chain-extend passes=${guard - 1} components=${components.size} real=${real.size} " +
                    "primarySize=${primary.size} finalBounds=[${bounds.x0},${bounds.y0},${bounds.x1},${bounds.y1}]"
            )
        }
        // Candidate danglers: small relative to the main piece (a real
        // ghungroo/bead is a fraction of the body's size, not comparable
        // to it -- that's what separates this from the pair-union above,
        // which unions comparably-SIZED components like a second earring)
        // and sitting in the lower ~45% of the piece's own bounds, where
        // hanging elements actually are.
        val danglerRowThreshold = bestMinRow + ((bestMaxRow - bestMinRow) * 0.55f).toInt()
        val danglerBlobs = real.filter { c ->
            c !== primary && c.size < primary.size * 0.15f && c.minRow >= danglerRowThreshold
        }.map { c ->
            Bounds(
                x0 = (startX + c.minCol * step).toFloat() / width,
                y0 = (startY + c.minRow * step).toFloat() / height,
                x1 = (startX + (c.maxCol + 1) * step).toFloat() / width,
                y1 = (startY + (c.maxRow + 1) * step).toFloat() / height
            )
        }
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
            points = points,
            highlightClipFraction = highlightClipFraction,
            sceneClipFraction = sceneClipFraction,
            danglerBlobs = danglerBlobs
        )
    }

    /**
     * Gold-only analysis for decoded Sony Live View JPEGs. This uses the
     * same RGB gold classifier, local-texture gate, guide/full-frame
     * geometry, component selection, pair union, and material thresholds
     * as [analyse] does for CameraX YUV frames. Silver/sparkle sampling is
     * intentionally omitted: Sony auto-steering must never redirect the
     * physical gimbal toward a neutral background highlight.
     */
    @Synchronized
    fun analyse(
        bitmap: Bitmap,
        step: Int = 6,
        fullFrame: Boolean = false,
        region: Bounds? = null,
        // Crops OUT a top strip in fullFrame mode only (2026-08-28,
        // explicit request): a long TOP_RAIL item's ring light physically
        // sits above the rail, and pinning long items to max zoom-out (see
        // MainActivity's isLongItemCategory) now brings that light itself
        // into frame. Left unexcluded it inflated sceneClipFraction (the
        // light's own blown-out pixels, not the jewellery's) and drove
        // applyAutoExposure() to step EV down repeatedly chasing a
        // brightness problem that was never on the ornament, darkening the
        // actual piece until tracking lost it. Does not affect the
        // centered-ROI or default-region paths -- those already exclude
        // the frame edges entirely.
        excludeTopFraction: Float = 0f
    ): Result {
        val width = bitmap.width
        val height = bitmap.height
        if (width <= 0 || height <= 0) return Result(false, null, 0f, 0f, 0f, 0f)

        val pixelCount = width * height
        if (bitmapArgbBuffer.size < pixelCount) bitmapArgbBuffer = IntArray(pixelCount)
        bitmap.getPixels(bitmapArgbBuffer, 0, width, 0, 0, width, height)

        // Sony composition lock: after full-frame acquisition and centering,
        // analyse only the padded category silhouette rectangle. This drops
        // warm reflections/stand edges outside the expected item position.
        // Caller clears the lock immediately on loss, returning here with
        // fullFrame=true so a misplaced item always self-recovers.
        val validRegion = region?.takeIf {
            !fullFrame && it.x1 > it.x0 && it.y1 > it.y0
        }
        val startX = when {
            fullFrame -> 0
            validRegion != null -> (width * validRegion.x0.coerceIn(0f, 0.98f)).toInt()
            else -> (width * 0.18).toInt()
        }
        val endX = when {
            fullFrame -> width
            validRegion != null -> (width * validRegion.x1.coerceIn(0.02f, 1f)).toInt()
            else -> (width * 0.82).toInt()
        }.coerceAtLeast(startX + 1)
        val startY = when {
            fullFrame -> (height * excludeTopFraction.coerceIn(0f, 0.4f)).toInt()
            validRegion != null -> (height * validRegion.y0.coerceIn(0f, 0.98f)).toInt()
            else -> (height * 0.16).toInt()
        }
        val endY = when {
            fullFrame -> height
            validRegion != null -> (height * validRegion.y1.coerceIn(0.02f, 1f)).toInt()
            else -> (height * 0.84).toInt()
        }.coerceAtLeast(startY + 1)
        val cols = max(1, (endX - startX) / step)
        val rows = max(1, (endY - startY) / step)
        val goldMask = BooleanArray(cols * rows)
        var goldSamples = 0
        var goldClipped = 0
        var sceneSamples = 0
        var sceneClipped = 0

        fun rgbAt(x: Int, y: Int): Int = bitmapArgbBuffer[y * width + x]
        fun luma(pixel: Int): Int {
            val r = pixel ushr 16 and 0xFF
            val g = pixel ushr 8 and 0xFF
            val b = pixel and 0xFF
            return (0.299f * r + 0.587f * g + 0.114f * b).toInt()
        }
        fun locallyTextured(cx: Int, cy: Int): Boolean {
            var sum = 0
            var sumSq = 0
            var count = 0
            var yy = cy - LOCAL_CONTRAST_RADIUS
            while (yy <= cy + LOCAL_CONTRAST_RADIUS) {
                if (yy in 0 until height) {
                    var xx = cx - LOCAL_CONTRAST_RADIUS
                    while (xx <= cx + LOCAL_CONTRAST_RADIUS) {
                        if (xx in 0 until width) {
                            val value = luma(rgbAt(xx, yy))
                            sum += value
                            sumSq += value * value
                            count += 1
                        }
                        xx += 2
                    }
                }
                yy += 2
            }
            if (count < 4) return false
            val mean = sum.toFloat() / count
            return (sumSq.toFloat() / count) - mean * mean >= MIN_LOCAL_VARIANCE
        }

        for (row in 0 until rows) {
            for (col in 0 until cols) {
                val x = min(width - 1, startX + col * step)
                val y = min(height - 1, startY + row * step)
                val pixel = rgbAt(x, y)
                val r = pixel ushr 16 and 0xFF
                val g = pixel ushr 8 and 0xFF
                val b = pixel and 0xFF
                val yLuma = luma(pixel)
                sceneSamples += 1
                if (yLuma >= 200) sceneClipped += 1
                if (looksLikeGold(r, g, b) && locallyTextured(x, y)) {
                    goldMask[row * cols + col] = true
                    goldSamples += 1
                    if (yLuma >= 240) goldClipped += 1
                }
            }
        }

        val points = ArrayList<Point>(goldSamples)
        for (row in 0 until rows) {
            for (col in 0 until cols) {
                if (!goldMask[row * cols + col]) continue
                val x = min(width - 1, startX + col * step)
                val y = min(height - 1, startY + row * step)
                points.add(Point(x.toFloat() / width, y.toFloat() / height, gold = true))
            }
        }
        val highlightClip = if (goldSamples > 0) goldClipped.toFloat() / goldSamples else 0f
        val sceneClip = if (sceneSamples > 0) sceneClipped.toFloat() / sceneSamples else 0f
        if (goldSamples == 0) return Result(false, null, 0f, 0f, 0f, 0f, points, highlightClip, sceneClip)

        data class BitmapComponent(
            val size: Int,
            val minCol: Int,
            val minRow: Int,
            val maxCol: Int,
            val maxRow: Int
        )

        val visited = BooleanArray(goldMask.size)
        val components = mutableListOf<BitmapComponent>()
        val stack = ArrayDeque<Int>()
        for (start in goldMask.indices) {
            if (!goldMask[start] || visited[start]) continue
            var size = 0
            var minCol = cols
            var minRow = rows
            var maxCol = -1
            var maxRow = -1
            stack.clear()
            stack.addLast(start)
            visited[start] = true
            while (stack.isNotEmpty()) {
                val current = stack.removeLast()
                size += 1
                val row = current / cols
                val col = current % cols
                minCol = min(minCol, col)
                minRow = min(minRow, row)
                maxCol = max(maxCol, col)
                maxRow = max(maxRow, row)
                for (dy in -1..1) for (dx in -1..1) {
                    if (dx == 0 && dy == 0) continue
                    val nr = row + dy
                    val nc = col + dx
                    if (nr !in 0 until rows || nc !in 0 until cols) continue
                    val next = nr * cols + nc
                    if (goldMask[next] && !visited[next]) {
                        visited[next] = true
                        stack.addLast(next)
                    }
                }
            }
            components.add(BitmapComponent(size, minCol, minRow, maxCol, maxRow))
        }
        if (components.isEmpty()) return Result(false, null, 0f, 0f, 0f, 0f, points, highlightClip, sceneClip)

        fun fillRatio(c: BitmapComponent): Float {
            val boxCells = (c.maxCol - c.minCol + 1) * (c.maxRow - c.minRow + 1)
            return c.size.toFloat() / max(1, boxCells)
        }
        fun edgesTouched(c: BitmapComponent): Int {
            var count = 0
            if (c.minCol <= 1) count += 1
            if (c.maxCol >= cols - 2) count += 1
            if (c.minRow <= 1) count += 1
            if (c.maxRow >= rows - 2) count += 1
            return count
        }

        val real = components.filter { fillRatio(it) >= 0.28f || edgesTouched(it) < 2 }
        val primary = real.maxByOrNull { it.size } ?: components.maxByOrNull { it.size }!!
        var bestMinCol = primary.minCol
        var bestMinRow = primary.minRow
        var bestMaxCol = primary.maxCol
        var bestMaxRow = primary.maxRow
        var bestSize = primary.size
        for (component in real) {
            if (component === primary || component.size < primary.size * 0.25f) continue
            bestMinCol = min(bestMinCol, component.minCol)
            bestMinRow = min(bestMinRow, component.minRow)
            bestMaxCol = max(bestMaxCol, component.maxCol)
            bestMaxRow = max(bestMaxRow, component.maxRow)
            bestSize += component.size
        }

        val bounds = Bounds(
            (startX + bestMinCol * step).toFloat() / width,
            (startY + bestMinRow * step).toFloat() / height,
            (startX + (bestMaxCol + 1) * step).toFloat() / width,
            (startY + (bestMaxRow + 1) * step).toFloat() / height
        )
        val danglerThreshold = bestMinRow + ((bestMaxRow - bestMinRow) * 0.55f).toInt()
        val danglers = real.filter {
            it !== primary && it.size < primary.size * 0.15f && it.minRow >= danglerThreshold
        }.map {
            Bounds(
                (startX + it.minCol * step).toFloat() / width,
                (startY + it.minRow * step).toFloat() / height,
                (startX + (it.maxCol + 1) * step).toFloat() / width,
                (startY + (it.maxRow + 1) * step).toFloat() / height
            )
        }

        val warmCoverage = bestSize.toFloat() / goldMask.size
        val scannedFraction = ((endX - startX).toFloat() / width) * ((endY - startY).toFloat() / height)
        val fullFrameGoldCoverage = warmCoverage * scannedFraction
        val goldBoxArea = bounds.area()
        val material = warmCoverage >= 0.06f || fullFrameGoldCoverage >= 0.012f || goldBoxArea >= 0.035f
        return Result(
            material,
            bounds,
            goldBoxArea,
            warmCoverage,
            fullFrameGoldCoverage,
            goldBoxArea,
            points,
            highlightClip,
            sceneClip,
            danglers
        )
    }
}
