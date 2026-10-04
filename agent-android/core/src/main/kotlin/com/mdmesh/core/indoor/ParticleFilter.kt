package com.mdmesh.core.indoor

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.sin
import kotlin.math.sqrt
import kotlin.random.Random

/** A position estimate: where, and how unsure ([spreadM] is the standard deviation of the particle cloud, in metres). */
data class IndoorEstimate(val at: Pt, val spreadM: Double)

/**
 * Particle-filter indoor positioning: fuses step tracking (PDR) with Wi-Fi fingerprint matching, constrained by the
 * floor plan.
 *
 *  - [step] moves every particle by one walked step (with noise on length and heading); a particle that would cross a
 *    wall or leave the plan is discarded, so drift cannot walk the estimate through a wall.
 *  - [observe] weights particles by how well a live Wi-Fi scan matches the survey at that particle's position, then
 *    resamples. Standing still, repeated observations alone narrow the cloud.
 *
 * Not thread-safe; use from one thread.
 */
class ParticleFilter(
    private val plan: FloorPlan,
    private val survey: FingerprintMap,
    private val count: Int = 600,
    private val random: Random = Random.Default,
) {
    private var xs = DoubleArray(count)
    private var ys = DoubleArray(count)
    private var w = DoubleArray(count) { 1.0 / count }

    init { scatter() }

    /** Spread particles uniformly over the plan (used at start and when the filter is lost). */
    fun scatter() {
        for (i in 0 until count) {
            xs[i] = random.nextDouble() * plan.widthM
            ys[i] = random.nextDouble() * plan.heightM
            w[i] = 1.0 / count
        }
    }

    /** Move by one detected step of [lengthM] along [headingRad] (0 = east, counter-clockwise positive). */
    fun step(lengthM: Double, headingRad: Double) {
        var alive = 0
        for (i in 0 until count) {
            val len = lengthM * (1.0 + gauss() * STEP_LENGTH_NOISE)
            val hdg = headingRad + gauss() * HEADING_NOISE
            val from = Pt(xs[i], ys[i])
            val to = Pt(from.x + len * cos(hdg), from.y + len * sin(hdg))
            if (plan.canMove(from, to)) {
                xs[i] = to.x; ys[i] = to.y
                alive++
            } else {
                w[i] = 0.0 // walked into a wall or out of the store
            }
        }
        if (alive == 0) { scatter() } else { normalise(); resampleIfNeeded() }
    }

    /** Correct the position with a live Wi-Fi scan (BSSID -> dBm). */
    fun observe(scan: Map<String, Int>) {
        if (scan.isEmpty()) return
        var total = 0.0
        for (i in 0 until count) {
            w[i] *= survey.likelihood(Pt(xs[i], ys[i]), scan)
            total += w[i]
        }
        if (total <= 1e-300) { scatter(); return }
        normalise()
        resample()
        // Small jitter so identical particles can keep exploring after resampling, when the device is standing still.
        for (i in 0 until count) {
            val nx = xs[i] + gauss() * ROUGHEN
            val ny = ys[i] + gauss() * ROUGHEN
            if (plan.canMove(Pt(xs[i], ys[i]), Pt(nx, ny))) { xs[i] = nx; ys[i] = ny }
        }
    }

    fun estimate(): IndoorEstimate {
        var mx = 0.0
        var my = 0.0
        for (i in 0 until count) { mx += w[i] * xs[i]; my += w[i] * ys[i] }
        var v = 0.0
        for (i in 0 until count) { v += w[i] * ((xs[i] - mx) * (xs[i] - mx) + (ys[i] - my) * (ys[i] - my)) }
        return IndoorEstimate(Pt(mx, my), sqrt(v))
    }

    private fun normalise() {
        val total = w.sum()
        if (total <= 0.0) { for (i in 0 until count) w[i] = 1.0 / count; return }
        for (i in 0 until count) w[i] /= total
    }

    private fun resampleIfNeeded() {
        var sq = 0.0
        for (i in 0 until count) sq += w[i] * w[i]
        if (1.0 / max(sq, 1e-300) < count / 2.0) resample()
    }

    /** Systematic resampling: heavier particles are copied more often. */
    private fun resample() {
        val nx = DoubleArray(count)
        val ny = DoubleArray(count)
        val start = random.nextDouble() / count
        var cumulative = w[0]
        var j = 0
        for (i in 0 until count) {
            val target = start + i.toDouble() / count
            while (target > cumulative && j < count - 1) { j++; cumulative += w[j] }
            nx[i] = xs[j]; ny[i] = ys[j]
        }
        xs = nx; ys = ny
        for (i in 0 until count) w[i] = 1.0 / count
    }

    /** Standard normal sample (Box-Muller). */
    private fun gauss(): Double {
        val u1 = max(random.nextDouble(), 1e-12)
        val u2 = random.nextDouble()
        return sqrt(-2.0 * Math.log(u1)) * cos(2.0 * PI * u2)
    }

    private companion object {
        const val STEP_LENGTH_NOISE = 0.10
        const val HEADING_NOISE = 0.12
        const val ROUGHEN = 0.15
    }
}

/** Straight-line distance between two points, in metres. */
fun distance(a: Pt, b: Pt): Double = hypot(a.x - b.x, a.y - b.y)
