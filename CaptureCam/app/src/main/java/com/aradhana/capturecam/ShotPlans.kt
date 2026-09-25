package com.aradhana.capturecam

/**
 * Per-category shot plan (2026-09-25), from the owner's ornament_shot_plan.xlsx.
 * Categories not listed fall back to [Plan.MAIN_PLUS_SIDES], i.e. the
 * long-standing MAIN + two side angles.
 *
 * Keep in step with shot_plans.py / config/shot_plans.json on the server, which
 * owns the "no shoot needed" list used to prune the shoot schedule.
 */
object ShotPlans {
    enum class Plan {
        /** Not photographed at all (gold coins, HAAR CHAIN 22). */
        NO_SHOOT,
        /** One shot: MAIN only. */
        MAIN_ONLY,
        /** MAIN + side angle 1 + side angle 2 (the default). */
        MAIN_PLUS_SIDES,
        /** MAIN (whole piece) + two zooms into different areas of the chain design. */
        CHAIN_TWO_DESIGN_ZOOMS,
        /** MAIN + chain-design zoom + (pendant zoom if a pendant is present, else a second design zoom). */
        CHAIN_DESIGN_PLUS_PENDANT
    }

    private val mainOnly = setOf("baby_braclet_22", "dull_22", "gents_bracelet_22")
    private val chainTwoZooms = setOf("chain_22", "fancy_mala_18", "fancy_mala_22")
    private val chainPendant = setOf(
        "ms_long_22", "mss_short_20", "mss_short_22", "necklace_22",
        "necklace_set_18", "necklace_set_22"
    )
    private val noShootKeys = setOf("haar_chain_22")

    fun forCategory(key: String?): Plan {
        val k = key?.trim()?.lowercase() ?: return Plan.MAIN_PLUS_SIDES
        return when {
            k.startsWith("gold_coin_") || k in noShootKeys -> Plan.NO_SHOOT
            k in mainOnly -> Plan.MAIN_ONLY
            k in chainTwoZooms -> Plan.CHAIN_TWO_DESIGN_ZOOMS
            k in chainPendant -> Plan.CHAIN_DESIGN_PLUS_PENDANT
            else -> Plan.MAIN_PLUS_SIDES
        }
    }
}
