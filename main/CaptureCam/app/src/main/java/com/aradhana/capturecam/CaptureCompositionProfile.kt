package com.aradhana.capturecam

import kotlin.math.min
import kotlin.math.sqrt

/** Category-specific capture geometry for the 57 exact stock categories.
 * Karat/weight variants share physical composition where appropriate, but
 * every stock key is explicitly mapped so an unknown category never gets a
 * confidently wrong guide.
 *
 * Shapes and size bands mirror JewelleryCatalogTool/category_orientation.py
 * and docs/jewellery_category_orientation_reference.md. Physical dimensions
 * are displayed/arranged bounds on the TYL stand, not chain circumference.
 */
object CaptureCompositionProfiles {
    enum class Silhouette {
        RING, CIRCLE, OPEN_CURVE, HOOP_PAIR, STUD_PAIR, DROP_PAIR,
        LONG_VERTICAL, NECK_CURVE, PENDANT, PENDANT_SET, CRESCENT,
        WATI, COIN, ARMLET
    }

    enum class Mount(val instruction: String) {
        TOP_RAIL("Use top rail; center the drape"),
        MIDDLE_RAIL("Use middle rail; equal spacing left/right"),
        LOWER_RAIL("Use lower rail; keep the full circle visible"),
        CLEAR_SUPPORT("Use a clear support stick; face toward camera"),
        BASE("Use the clear base; lay face-up and level")
    }

    data class Profile(
        val categoryKey: String,
        val label: String,
        val silhouette: Silhouette,
        val mount: Mount,
        val targetAspect: Float,
        val targetArea: Float,
        val displayedWidthMm: Float? = null,
        val displayedHeightMm: Float? = null,
        val sizeConfidence: String = "low"
    ) {
        /** A visually square item is not a 1:1 normalized box inside a 3:2
         * image. Convert physical W:H to normalized-frame W:H first. */
        val normalizedFrameAspect: Float
            get() = targetAspect /
                (CaptureHardwareProfile.SENSOR_WIDTH_MM / CaptureHardwareProfile.SENSOR_HEIGHT_MM)

        /** Safe centered guide, preserving the category's researched shape. */
        fun targetFrame(): Pair<Float, Float> {
            var width = sqrt(targetArea * normalizedFrameAspect)
            var height = sqrt(targetArea / normalizedFrameAspect)
            val scale = min(0.88f / width, 0.82f / height).coerceAtMost(1f)
            width *= scale
            height *= scale
            return width to height
        }

        fun detectorRegion(padding: Float = 1.22f): MaterialDetector.Bounds {
            val (targetWidth, targetHeight) = targetFrame()
            val width = (targetWidth * padding).coerceAtMost(0.96f)
            val height = (targetHeight * padding).coerceAtMost(0.96f)
            return MaterialDetector.Bounds(
                0.5f - width / 2f,
                0.5f - height / 2f,
                0.5f + width / 2f,
                0.5f + height / 2f
            )
        }

        fun opticalPlan(): CaptureHardwareProfile.TelePlan? {
            val widthMm = displayedWidthMm ?: return null
            val heightMm = displayedHeightMm ?: return null
            val (targetWidth, targetHeight) = targetFrame()
            return CaptureHardwareProfile.telePlan(widthMm, heightMm, targetWidth, targetHeight)
        }
    }

    private fun profile(
        key: String,
        label: String,
        silhouette: Silhouette,
        mount: Mount,
        aspect: Float,
        area: Float,
        widthMm: Float? = null,
        heightMm: Float? = null,
        confidence: String = "low"
    ) = Profile(key, label, silhouette, mount, aspect, area, widthMm, heightMm, confidence)

    val BY_CATEGORY: Map<String, Profile> = listOf(
        profile("baby_braclet_22", "BABY BRACLET 22", Silhouette.OPEN_CURVE, Mount.LOWER_RAIL, 3.0f, 0.24f, 100f, 34f),
        profile("baby_kadli_22", "BABY KADLI 22", Silhouette.CIRCLE, Mount.CLEAR_SUPPORT, 1.0f, 0.16f, 38f, 38f, "moderate"),
        profile("baby_ring_22", "BABY RING 22", Silhouette.RING, Mount.CLEAR_SUPPORT, 1.0f, 0.025f, 14f, 14f),
        profile("baju_bandh_22", "BAJU BANDH 22", Silhouette.ARMLET, Mount.LOWER_RAIL, 2.5f, 0.38f, 120f, 48f),
        profile("bali_18", "BALI 18", Silhouette.HOOP_PAIR, Mount.MIDDLE_RAIL, 1.25f, 0.28f, 70f, 45f, "high"),
        profile("bali_22", "BALI 22", Silhouette.HOOP_PAIR, Mount.MIDDLE_RAIL, 1.25f, 0.28f, 70f, 45f, "high"),
        profile("bangle_22", "BANGLE 22", Silhouette.CIRCLE, Mount.LOWER_RAIL, 1.0f, 0.44f, 62f, 62f, "moderate"),
        // NECK_CURVE/TOP_RAIL aspect+dims corrected 2026-08-28: old values
        // (wide, laid-flat-on-a-table convention) don't match how this rig
        // presents a top-rail-hung item. Live-measured directly on
        // ms_long_22 pinned to max zoom-out (162 samples, ratio~0.25-0.29,
        // ~72% of readings) -- see that entry's own comment. Siblings share
        // identical physical mounting so get the same corrected aspect;
        // heightMm kept close to the original width (the chain's real
        // material length carries over from laid-flat to hung), widthMm
        // derived from the corrected aspect -- unverified per-sibling,
        // confirm live when tested.
        profile("chain_22", "CHAIN 22", Silhouette.NECK_CURVE, Mount.TOP_RAIL, 0.28f, 0.52f, 59f, 210f, "moderate"),
        profile("dull_22", "DULL 22", Silhouette.STUD_PAIR, Mount.MIDDLE_RAIL, 2.0f, 0.055f, 34f, 14f),
        profile("earring_22", "EARRING 22", Silhouette.DROP_PAIR, Mount.MIDDLE_RAIL, 0.9f, 0.24f, 60f, 60f),
        profile("fancy_mala_18", "FANCY MALA 18", Silhouette.NECK_CURVE, Mount.TOP_RAIL, 0.28f, 0.56f, 62f, 220f, "moderate"),
        profile("fancy_mala_22", "FANCY MALA 22", Silhouette.NECK_CURVE, Mount.TOP_RAIL, 0.28f, 0.56f, 62f, 220f, "moderate"),
        profile("gents_bracelet_22", "GENTS BRACELET 22", Silhouette.OPEN_CURVE, Mount.LOWER_RAIL, 3.25f, 0.34f, 115f, 35f, "high"),
        profile("gents_kada_18", "GENTS KADA 18", Silhouette.CIRCLE, Mount.LOWER_RAIL, 1.0f, 0.48f, 70f, 70f, "moderate"),
        profile("gents_kada_22", "GENTS KADA 22", Silhouette.CIRCLE, Mount.LOWER_RAIL, 1.0f, 0.48f, 70f, 70f, "moderate"),
        profile("gents_ring_22", "GENTS RING 22", Silhouette.RING, Mount.CLEAR_SUPPORT, 1.0f, 0.060f, 23f, 23f, "moderate"),
        profile("haar_chain_22", "HAAR CHAIN 22", Silhouette.NECK_CURVE, Mount.TOP_RAIL, 0.28f, 0.52f, 59f, 210f),
        profile("jhumka_22", "JHUMKA 22", Silhouette.DROP_PAIR, Mount.MIDDLE_RAIL, 0.85f, 0.30f, 70f, 65f, "moderate"),
        profile("kaan_chain_22", "KAAN CHAIN 22", Silhouette.LONG_VERTICAL, Mount.TOP_RAIL, 0.22f, 0.14f, 35f, 160f, "moderate"),
        profile("ladies_bracelet_18", "LADIES BRACELET 18", Silhouette.OPEN_CURVE, Mount.LOWER_RAIL, 3.25f, 0.30f, 100f, 31f),
        profile("ladies_bracelet_22", "LADIES BRACELET 22", Silhouette.OPEN_CURVE, Mount.LOWER_RAIL, 3.25f, 0.30f, 100f, 31f),
        profile("ladies_kada_22", "LADIES KADA 22", Silhouette.CIRCLE, Mount.LOWER_RAIL, 1.0f, 0.43f, 60f, 60f),
        profile("ladies_ring_18", "LADIES RING 18", Silhouette.RING, Mount.CLEAR_SUPPORT, 1.0f, 0.050f, 20f, 20f, "moderate"),
        profile("ladies_ring_22", "LADIES RING 22", Silhouette.RING, Mount.CLEAR_SUPPORT, 1.0f, 0.050f, 20f, 20f, "moderate"),
        profile("locket_18", "LOCKET 18", Silhouette.PENDANT, Mount.CLEAR_SUPPORT, 0.78f, 0.16f, 28f, 36f),
        profile("locket_22", "LOCKET 22", Silhouette.PENDANT, Mount.CLEAR_SUPPORT, 0.78f, 0.16f, 28f, 36f),
        profile("mangota_22", "MANGOTA 22", Silhouette.OPEN_CURVE, Mount.LOWER_RAIL, 3.0f, 0.25f, 100f, 34f, "moderate"),
        profile("moti_nath_18", "MOTI NATH 18", Silhouette.CRESCENT, Mount.CLEAR_SUPPORT, 1.75f, 0.28f, 65f, 38f),
        // Live-confirmed 2026-08-28: operator report + logcat both showed a
        // real, correctly-hung MS LONG 22 measuring ratio~0.28 tick after
        // tick (162 samples) against the OLD 1.3-1.7 range -- permanently
        // blocked capture ("Reposition -- tracking looks off" forever). An
        // intermediate reciprocal-based guess (0.667) was still ~2.4x too
        // high; this value is the directly measured one.
        profile("ms_long_22", "MS LONG 22", Silhouette.NECK_CURVE, Mount.TOP_RAIL, 0.28f, 0.58f, 62f, 220f, "moderate"),
        profile("mss_short_20", "MSS-SHORT 20", Silhouette.NECK_CURVE, Mount.TOP_RAIL, 0.28f, 0.52f, 57f, 205f, "moderate"),
        profile("mss_short_22", "MSS-SHORT 22", Silhouette.NECK_CURVE, Mount.TOP_RAIL, 0.28f, 0.52f, 57f, 205f, "moderate"),
        profile("nath_22", "NATH 22", Silhouette.CRESCENT, Mount.CLEAR_SUPPORT, 1.75f, 0.26f, 60f, 35f),
        profile("necklace_22", "NECKLACE 22", Silhouette.NECK_CURVE, Mount.TOP_RAIL, 0.28f, 0.56f, 60f, 215f),
        profile("necklace_set_18", "NECKLACE SET 18", Silhouette.PENDANT_SET, Mount.TOP_RAIL, 1.15f, 0.58f, 200f, 180f),
        profile("necklace_set_22", "NECKLACE SET 22", Silhouette.PENDANT_SET, Mount.TOP_RAIL, 1.15f, 0.58f, 200f, 180f),
        profile("pendent_18", "PENDENT 18", Silhouette.PENDANT, Mount.CLEAR_SUPPORT, 0.72f, 0.14f, 25f, 35f, "high"),
        profile("pendent_22", "PENDENT 22", Silhouette.PENDANT, Mount.CLEAR_SUPPORT, 0.72f, 0.14f, 25f, 35f, "high"),
        profile("pendent_set_18", "PENDENT SET 18", Silhouette.PENDANT_SET, Mount.MIDDLE_RAIL, 0.9f, 0.38f, 75f, 80f),
        profile("pendent_set_22", "PENDENT SET 22", Silhouette.PENDANT_SET, Mount.MIDDLE_RAIL, 0.9f, 0.38f, 75f, 80f),
        profile("tikka_22", "TIKKA 22", Silhouette.LONG_VERTICAL, Mount.TOP_RAIL, 0.22f, 0.15f, 30f, 120f, "moderate"),
        profile("tops_18", "TOPS 18", Silhouette.STUD_PAIR, Mount.MIDDLE_RAIL, 2.0f, 0.055f, 34f, 14f),
        profile("tops_22", "TOPS 22", Silhouette.STUD_PAIR, Mount.MIDDLE_RAIL, 2.0f, 0.055f, 34f, 14f),
        profile("wati_22", "WATI 22", Silhouette.WATI, Mount.CLEAR_SUPPORT, 2.25f, 0.075f, 32f, 14f, "high")
    ).associateBy { it.categoryKey }.toMutableMap().apply {
        val coinKeys = listOf(
            "gold_coin_22_kt" to "GOLD COIN 22 KT",
            "gold_coin_0_025_m" to "Gold Coin 0.025 M",
            "gold_coin_0_050_m" to "Gold Coin 0.050 M",
            "gold_coin_0_100_m" to "Gold Coin 0.100 M",
            "gold_coin_0_200_m" to "Gold Coin 0.200 M",
            "gold_coin_0_250_m" to "Gold Coin 0.250 M",
            "gold_coin_0_300_m" to "Gold Coin 0.300 M",
            "gold_coin_0_500_m" to "Gold Coin 0.500 M",
            "gold_coin_0_750_m" to "Gold Coin 0.750 M",
            "gold_coin_1_gm" to "Gold Coin 1 Gm",
            "gold_coin_10_gm" to "Gold Coin 10 Gm",
            "gold_coin_2_gm" to "Gold Coin 2 Gm",
            "gold_coin_20_gm" to "Gold Coin 20 Gm",
            "gold_coin_5_gm" to "Gold Coin 5 Gm"
        )
        coinKeys.forEach { (key, label) ->
            put(key, profile(key, label, Silhouette.COIN, Mount.BASE, 1f, 0.045f))
        }
    }

    init {
        // Soft check, not a hard crash (2026-08-26): a hard check() here
        // crashed the WHOLE app on launch if the catalogue's stock-category
        // count ever drifted from exactly 57 -- one operator-side catalogue
        // edit would take down capture entirely with no diagnostic on
        // screen. Log loudly instead; forCategory() already returns null
        // safely for any unmapped key, so a mismatch degrades to "no
        // composition guide for this one category" rather than "app won't
        // open."
        if (BY_CATEGORY.size != 57) {
            android.util.Log.e(
                "CaptureCompositionProfiles",
                "Expected all 57 stock categories, got ${BY_CATEGORY.size} -- " +
                    "composition guidance will be missing for any category not in this map"
            )
        }
    }

    fun forCategory(categoryKey: String?): Profile? = categoryKey?.let(BY_CATEGORY::get)
}
