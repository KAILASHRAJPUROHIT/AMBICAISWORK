package com.aradhana.capturecam

import android.graphics.Bitmap
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.max

/**
 * Deterministic viewfinder aids computed from Sony's clean Live View JPEG.
 * These pixels are display-only. The camera original is never modified.
 *
 * Sony's HTTP LiveViewDataset exposes AF lock state but not the camera LCD's
 * rendered peaking/zebra/histogram pixels. Recompute the equivalent visual
 * aids locally from the same frame instead of pretending detector dots are
 * focus peaking.
 */
object CameraAssistAnalyzer {
    enum class MarkKind { PEAKING, HIGHLIGHT_CLIP, SHADOW_CLIP }

    data class Mark(val x: Float, val y: Float, val kind: MarkKind)

    data class Result(
        val marks: List<Mark>,
        /** 32 luminance bins, normalized so the tallest bin is 1. */
        val histogram: FloatArray,
        val shadowClipFraction: Float,
        val highlightClipFraction: Float
    ) {
        val exposureOk: Boolean
            get() = shadowClipFraction <= SHADOW_OK_FRACTION &&
                highlightClipFraction <= HIGHLIGHT_OK_FRACTION
    }

    private var argbBuffer = IntArray(0)

    /**
     * One sparse full-frame exposure pass plus one ornament-ROI detail pass.
     * Work is bounded and runs on MainActivity's existing Sony analysis
     * thread, never on the 25fps render path.
     */
    @Synchronized
    fun analyse(bitmap: Bitmap, ornament: MaterialDetector.Bounds?): Result {
        val width = bitmap.width
        val height = bitmap.height
        if (width < 5 || height < 5) {
            return Result(emptyList(), FloatArray(HISTOGRAM_BINS), 0f, 0f)
        }
        val required = width * height
        if (argbBuffer.size < required) argbBuffer = IntArray(required)
        bitmap.getPixels(argbBuffer, 0, width, 0, 0, width, height)

        val bins = IntArray(HISTOGRAM_BINS)
        val highlightMarks = ArrayList<Mark>(MAX_CLIP_MARKS)
        val shadowMarks = ArrayList<Mark>(MAX_CLIP_MARKS)
        var sampled = 0
        var shadowClipped = 0
        var highlightClipped = 0
        // Scoped to the ornament ROI, same inset as the peaking pass below
        // (2026-08-26 fix): this used to scan the ENTIRE frame, so any
        // blown-out background, reflection, or gloved hand produced clip
        // marks scattered far outside the jewellery -- confirmed live, an
        // operator reported them as confusing "historical traces" since
        // they didn't track the ring at all. Falls back to full-frame when
        // no ornament is detected yet (e.g. TAG phase) so the exposure
        // aids still show something before framing starts.
        val clipX0: Int
        val clipX1: Int
        val clipY0: Int
        val clipY1: Int
        if (ornament != null) {
            val insetX = (ornament.x1 - ornament.x0) * PEAKING_BOUNDS_INSET
            val insetY = (ornament.y1 - ornament.y0) * PEAKING_BOUNDS_INSET
            clipX0 = ((ornament.x0 + insetX) * width).toInt().coerceIn(0, width - 1)
            clipX1 = ((ornament.x1 - insetX) * width).toInt().coerceIn(clipX0 + 1, width)
            clipY0 = ((ornament.y0 + insetY) * height).toInt().coerceIn(0, height - 1)
            clipY1 = ((ornament.y1 - insetY) * height).toInt().coerceIn(clipY0 + 1, height)
        } else {
            clipX0 = 0; clipX1 = width; clipY0 = 0; clipY1 = height
        }
        var y = clipY0
        while (y < clipY1) {
            var x = clipX0
            while (x < clipX1) {
                val pixel = argbBuffer[y * width + x]
                val r = (pixel ushr 16) and 0xFF
                val g = (pixel ushr 8) and 0xFF
                val b = pixel and 0xFF
                val luma = (r * 299 + g * 587 + b * 114) / 1000
                bins[(luma * HISTOGRAM_BINS / 256).coerceAtMost(HISTOGRAM_BINS - 1)] += 1
                sampled += 1
                if (luma <= SHADOW_LUMA_MAX) {
                    shadowClipped += 1
                    if (shadowMarks.size < MAX_CLIP_MARKS) {
                        shadowMarks += Mark(
                            x.toFloat() / width,
                            y.toFloat() / height,
                            MarkKind.SHADOW_CLIP
                        )
                    }
                }
                // A single saturated RGB channel can erase gold colour and
                // engraving detail even when overall luminance is below 255.
                if (max(r, max(g, b)) >= HIGHLIGHT_CHANNEL_MIN) {
                    highlightClipped += 1
                    if (highlightMarks.size < MAX_CLIP_MARKS) {
                        highlightMarks += Mark(
                            x.toFloat() / width,
                            y.toFloat() / height,
                            MarkKind.HIGHLIGHT_CLIP
                        )
                    }
                }
                x += EXPOSURE_SAMPLE_STEP
            }
            y += EXPOSURE_SAMPLE_STEP
        }

        val peakingCandidates = ArrayList<Mark>(MAX_PEAKING_MARKS * 2)
        ornament?.let { bounds ->
            val insetX = (bounds.x1 - bounds.x0) * PEAKING_BOUNDS_INSET
            val insetY = (bounds.y1 - bounds.y0) * PEAKING_BOUNDS_INSET
            val x0 = ((bounds.x0 + insetX) * width).toInt().coerceIn(1, width - 2)
            val x1 = ((bounds.x1 - insetX) * width).toInt().coerceIn(x0 + 1, width - 1)
            val y0 = ((bounds.y0 + insetY) * height).toInt().coerceIn(1, height - 2)
            val y1 = ((bounds.y1 - insetY) * height).toInt().coerceIn(y0 + 1, height - 1)
            var py = y0
            while (py < y1) {
                var px = x0
                while (px < x1) {
                    val center = lumaAt(px, py, width)
                    if (center in PEAKING_LUMA_MIN..PEAKING_LUMA_MAX) {
                        val left = lumaAt(px - 1, py, width)
                        val right = lumaAt(px + 1, py, width)
                        val up = lumaAt(px, py - 1, width)
                        val down = lumaAt(px, py + 1, width)
                        val gradient = abs(right - left) + abs(down - up)
                        val laplacian = abs(4 * center - left - right - up - down)
                        // Requiring both edge energy and local curvature
                        // rejects smooth silhouette edges and lights the
                        // small engraving/stone facets that contain detail.
                        if (gradient >= PEAKING_GRADIENT_MIN &&
                            laplacian >= PEAKING_LAPLACIAN_MIN
                        ) {
                            peakingCandidates += Mark(
                                px.toFloat() / width,
                                py.toFloat() / height,
                                MarkKind.PEAKING
                            )
                        }
                    }
                    px += PEAKING_SAMPLE_STEP
                }
                py += PEAKING_SAMPLE_STEP
            }
        }

        val peaking = if (peakingCandidates.size <= MAX_PEAKING_MARKS) {
            peakingCandidates
        } else {
            val stride = ceil(peakingCandidates.size.toDouble() / MAX_PEAKING_MARKS).toInt()
            ArrayList<Mark>(MAX_PEAKING_MARKS).apply {
                var index = 0
                while (index < peakingCandidates.size && size < MAX_PEAKING_MARKS) {
                    add(peakingCandidates[index])
                    index += stride
                }
            }
        }

        val maxBin = bins.maxOrNull()?.coerceAtLeast(1) ?: 1
        val histogram = FloatArray(HISTOGRAM_BINS) { bins[it].toFloat() / maxBin }
        val denominator = sampled.coerceAtLeast(1).toFloat()
        return Result(
            marks = ArrayList<Mark>(peaking.size + highlightMarks.size + shadowMarks.size).apply {
                addAll(peaking)
                addAll(highlightMarks)
                addAll(shadowMarks)
            },
            histogram = histogram,
            shadowClipFraction = shadowClipped / denominator,
            highlightClipFraction = highlightClipped / denominator
        )
    }

    private fun lumaAt(x: Int, y: Int, width: Int): Int {
        val pixel = argbBuffer[y * width + x]
        return (((pixel ushr 16) and 0xFF) * 299 +
            ((pixel ushr 8) and 0xFF) * 587 +
            (pixel and 0xFF) * 114) / 1000
    }

    private const val HISTOGRAM_BINS = 32
    private const val EXPOSURE_SAMPLE_STEP = 4
    private const val SHADOW_LUMA_MAX = 4
    private const val HIGHLIGHT_CHANNEL_MIN = 252
    private const val SHADOW_OK_FRACTION = 0.002f
    private const val HIGHLIGHT_OK_FRACTION = 0.001f
    private const val MAX_CLIP_MARKS = 700
    private const val MAX_PEAKING_MARKS = 1_200
    private const val PEAKING_SAMPLE_STEP = 2
    private const val PEAKING_BOUNDS_INSET = 0.03f
    private const val PEAKING_LUMA_MIN = 18
    private const val PEAKING_LUMA_MAX = 246
    private const val PEAKING_GRADIENT_MIN = 34
    private const val PEAKING_LAPLACIAN_MIN = 24
}
