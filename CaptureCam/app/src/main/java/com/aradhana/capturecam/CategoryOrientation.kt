package com.aradhana.capturecam

/**
 * On-device mirror of the relevant slice of
 * JewelleryCatalogTool/category_orientation.py (2026-08-19 research,
 * docs/jewellery_category_orientation_reference.md). Only carries what
 * MainActivity needs for the live ghungroo/dangler symmetry check --
 * category keys whose piece has a genuine mirror-symmetric pair or pair
 * of halves worth comparing left vs right (a matched earring/jhumka pair,
 * or WATI's twin-bowl pendant). Keep in sync with the Python module if
 * categories change there.
 */
object CategoryOrientation {
    val MIRROR_SYMMETRY_CATEGORIES = setOf(
        "bali_18", "bali_22", "tops_18", "tops_22", "dull_22",
        "earring_22", "jhumka_22", "kaan_chain_22", "moti_nath_18", "nath_22", "tikka_22",
        "wati_22"
    )

    fun hasMirrorSymmetry(categoryKey: String?): Boolean =
        categoryKey != null && categoryKey in MIRROR_SYMMETRY_CATEGORIES

    /** Mirror of category_orientation.py's GATE_WORTHY_CATEGORIES +
     * PROFILES[key].aspect_ratio -- only the hand-picked subset with
     * moderate/high size-confidence AND a shape far enough from 1:1 to be
     * a real signal (see that module's own doc comment for why the full
     * 57-category research isn't all gate-worthy). min/max is width:height
     * as the piece would be laid/worn for the capture photo. Built
     * directly in response to the 2026-08-19 bracelet mis-framing:
     * coverage/goldClip/sceneClip all read fine while the tracker had
     * locked onto a thin sub-segment of the band -- this catches "the
     * tracked blob's own shape doesn't look like what THIS category
     * should look like at all", independent of touchesFrameEdge (that
     * catches the item running off the visible frame; this catches a
     * partial/wrong-shaped read even when it's fully inside the frame). */
    data class AspectRange(val min: Float, val max: Float)

    val GATE_WORTHY_ASPECT: Map<String, AspectRange> = mapOf(
        "gents_bracelet_22" to AspectRange(3.0f, 3.5f),
        "ladies_bracelet_18" to AspectRange(3.0f, 3.5f),
        "ladies_bracelet_22" to AspectRange(3.0f, 3.5f),
        "mangota_22" to AspectRange(2.5f, 3.5f),
        "baby_braclet_22" to AspectRange(2.5f, 3.5f),
        // Corrected 2026-08-28 for these NECK_CURVE/TOP_RAIL categories:
        // the old ranges (1.2-1.8, "wide") came from category_orientation.
        // py's laid-flat-on-a-table convention, but this rig hangs TOP_RAIL
        // items from a rail (tall in-frame, not wide) -- a first pass
        // inverted the old ranges (reciprocal, ~0.6-0.8) but LIVE
        // measurement on ms_long_22 pinned to max zoom-out showed the real
        // ratio consistently at 0.25-0.29 (162 samples, ~72% in that
        // band), well below even the inverted guess. This range is
        // measured directly for ms_long_22; the siblings share identical
        // physical mounting so get the same corrected band, but only
        // ms_long_22 has live confirmation -- verify each sibling live
        // when tested.
        "chain_22" to AspectRange(0.24f, 0.34f),
        "fancy_mala_18" to AspectRange(0.24f, 0.34f),
        "fancy_mala_22" to AspectRange(0.24f, 0.34f),
        "ms_long_22" to AspectRange(0.24f, 0.34f),
        "mss_short_20" to AspectRange(0.24f, 0.34f),
        "mss_short_22" to AspectRange(0.24f, 0.34f),
        "wati_22" to AspectRange(2.0f, 2.5f),
        "pendent_18" to AspectRange(0.6f, 0.85f),
        "pendent_22" to AspectRange(0.6f, 0.85f),
        "jhumka_22" to AspectRange(0.4f, 0.5f),
        "kaan_chain_22" to AspectRange(0.067f, 0.125f),
        "tikka_22" to AspectRange(0.167f, 0.25f)
    )

    /** True if bounds' own width:height ratio is nowhere near what
     * categoryKey's real jewellery should look like -- a fixed 40% slack
     * on both ends of the sourced range, since this is a live capture-time
     * signal on a bounding box that jitters frame to frame, not a lab
     * measurement. Only categories in GATE_WORTHY_ASPECT are checked;
     * everything else (rings, studs, gold coins, or size data too thin to
     * trust) returns false -- fail open, never block on data we don't
     * trust. */
    fun looksWrongShape(categoryKey: String?, bounds: MaterialDetector.Bounds?): Boolean {
        if (categoryKey == null || bounds == null) return false
        val range = GATE_WORTHY_ASPECT[categoryKey] ?: return false
        val w = bounds.x1 - bounds.x0
        val h = bounds.y1 - bounds.y0
        if (w <= 0f || h <= 0f) return false
        val ratio = w / h
        val slack = 0.4f
        val lo = range.min * (1f - slack)
        val hi = range.max * (1f + slack)
        return ratio < lo || ratio > hi
    }
}
