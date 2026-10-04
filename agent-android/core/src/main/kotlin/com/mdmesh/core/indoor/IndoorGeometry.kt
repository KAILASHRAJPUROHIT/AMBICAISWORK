package com.mdmesh.core.indoor

import com.mdmesh.proto.IndoorBundleDto
import com.mdmesh.proto.IndoorPlanDto

/** Pure helpers turning the server's plan/survey DTOs into the engine's model. Kept free of Android for unit tests. */
object IndoorGeometry {

    fun floorPlan(plan: IndoorPlanDto): FloorPlan = FloorPlan(
        widthM = plan.widthM,
        heightM = plan.heightM,
        walls = plan.walls.filter { it.size == 4 }.map { Wall(Pt(it[0], it[1]), Pt(it[2], it[3])) },
    )

    fun fingerprintMap(bundle: IndoorBundleDto): FingerprintMap =
        FingerprintMap(bundle.points.filter { it.rssi.isNotEmpty() }.map { Fingerprint(Pt(it.x, it.y), it.rssi, it.mag) })

    /** Name of the zone containing ([x], [y]); when zones overlap the smallest one wins (a counter inside a hall). */
    fun zoneAt(plan: IndoorPlanDto, x: Double, y: Double): String? =
        plan.zones
            .filter { x >= it.x && x <= it.x + it.w && y >= it.y && y <= it.y + it.h }
            .minByOrNull { it.w * it.h }
            ?.name

    /**
     * Converts a compass bearing (degrees clockwise from true north, as the rotation-vector sensor reports it) into the
     * engine's heading: radians counter-clockwise from the plan's +x axis. [northDeg] is the bearing of the plan's
     * "up" (+y) direction.
     */
    fun planHeadingRad(bearingDeg: Double, northDeg: Double): Double =
        Math.toRadians((northDeg + 90.0) - bearingDeg)
}
