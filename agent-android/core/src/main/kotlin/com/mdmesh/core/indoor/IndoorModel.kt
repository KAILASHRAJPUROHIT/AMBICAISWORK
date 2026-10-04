package com.mdmesh.core.indoor

import kotlin.math.hypot

/** A point on the floor plan, in metres. x grows east, y grows north. */
data class Pt(val x: Double, val y: Double)

/** A wall segment. */
data class Wall(val a: Pt, val b: Pt)

/**
 * The store's floor plan: a rectangle [widthM] x [heightM] with [walls] inside it. Particles may not leave the
 * rectangle or step through a wall, which is what keeps step-tracking drift from walking a position through a counter
 * or into the next room.
 */
class FloorPlan(val widthM: Double, val heightM: Double, val walls: List<Wall> = emptyList()) {

    fun contains(p: Pt): Boolean = p.x in 0.0..widthM && p.y in 0.0..heightM

    /** True when the straight move [from] -> [to] is allowed: it stays inside the plan and crosses no wall. */
    fun canMove(from: Pt, to: Pt): Boolean = contains(to) && walls.none { segmentsIntersect(from, to, it.a, it.b) }

    private fun segmentsIntersect(p1: Pt, p2: Pt, q1: Pt, q2: Pt): Boolean {
        val d1 = cross(q1, q2, p1)
        val d2 = cross(q1, q2, p2)
        val d3 = cross(p1, p2, q1)
        val d4 = cross(p1, p2, q2)
        return (d1 * d2 < 0.0) && (d3 * d4 < 0.0)
    }

    private fun cross(a: Pt, b: Pt, c: Pt): Double = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)
}

/** One surveyed point: where it is on the plan and the signal strengths (dBm) heard there, keyed by BSSID. */
data class Fingerprint(val at: Pt, val rssi: Map<String, Int>)

/** The survey: every [Fingerprint] recorded while walking the store. */
class FingerprintMap(val points: List<Fingerprint>) {

    /**
     * Expected signal strengths at [p], blended from the [K] nearest surveyed points (closer points count more), or
     * null when nothing was surveyed.
     */
    fun expectedAt(p: Pt): Map<String, Double>? {
        if (points.isEmpty()) return null
        val nearest = points.sortedBy { hypot(it.at.x - p.x, it.at.y - p.y) }.take(K)
        val sums = HashMap<String, Double>()
        val weights = HashMap<String, Double>()
        for (fp in nearest) {
            val d = hypot(fp.at.x - p.x, fp.at.y - p.y)
            val w = 1.0 / (d * d + 0.25)
            for ((bssid, rssi) in fp.rssi) {
                sums[bssid] = (sums[bssid] ?: 0.0) + w * rssi
                weights[bssid] = (weights[bssid] ?: 0.0) + w
            }
        }
        return sums.mapValues { (k, v) -> v / weights.getValue(k) }
    }

    /**
     * How well a live [scan] (BSSID -> dBm) agrees with what the survey expects at [p]. Higher is better; the value is
     * a likelihood in (0, 1], softened so a single bad reading cannot wipe out a good position.
     */
    fun likelihood(p: Pt, scan: Map<String, Int>): Double {
        val expected = expectedAt(p) ?: return 1.0
        var sumSq = 0.0
        var used = 0
        val all = HashSet<String>().apply { addAll(expected.keys); addAll(scan.keys) }
        for (bssid in all) {
            val e = expected[bssid]
            val s = scan[bssid]
            // A network heard on one side only counts as "very weak" on the other, but only when it is clearly strong
            // where it was heard; faint networks flicker in and out and say nothing.
            val ev = e ?: if ((s ?: FLOOR) > AUDIBLE) FLOOR.toDouble() else continue
            val sv = s?.toDouble() ?: if (e!! > AUDIBLE) FLOOR.toDouble() else continue
            val diff = (sv - ev)
            sumSq += diff * diff
            used++
        }
        if (used == 0) return 1.0
        // Tempered Gaussian: readings are correlated, so treating them as independent would make the filter overconfident.
        return Math.exp(-TEMPER * sumSq / (2.0 * SIGMA * SIGMA * used.coerceAtLeast(1)) * used.coerceAtMost(MAX_EFFECTIVE))
    }

    private companion object {
        const val K = 4
        const val SIGMA = 6.0
        const val FLOOR = -100
        const val AUDIBLE = -85
        const val TEMPER = 1.0
        const val MAX_EFFECTIVE = 6
    }
}
