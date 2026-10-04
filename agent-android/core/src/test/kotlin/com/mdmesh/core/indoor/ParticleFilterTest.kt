package com.mdmesh.core.indoor

import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.random.Random
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Simulated 20 m x 10 m store with six access points, a surveyed 2 m grid and an interior wall. Signal strengths follow
 * a log-distance model with 4 dB of noise per reading, a deliberately harsh stand-in for a real shop. These tests pin
 * the engine's behaviour; the accuracy a real store achieves must be measured there.
 */
class ParticleFilterTest {

    private val aps = mapOf(
        "ap1" to Pt(1.0, 1.0), "ap2" to Pt(10.0, 0.5), "ap3" to Pt(19.0, 1.0),
        "ap4" to Pt(1.0, 9.0), "ap5" to Pt(10.0, 9.5), "ap6" to Pt(19.0, 9.0),
    )

    /** Wall at x = 10 from the south edge up to y = 7; a doorway between y = 7 and the north edge. */
    private val plan = FloorPlan(20.0, 10.0, listOf(Wall(Pt(10.0, 0.0), Pt(10.0, 7.0))))

    private fun rssi(from: Pt, ap: Pt, noise: Double, rnd: Random): Int {
        val d = max(distance(from, ap), 1.0)
        val wallPenalty = if (!plan.canMove(from, ap.copy())) 8.0 else 0.0
        return (-40.0 - 25.0 * log10(d) - wallPenalty + noise * gaussian(rnd)).roundToInt()
    }

    private fun scanAt(p: Pt, noise: Double, rnd: Random): Map<String, Int> =
        aps.mapValues { (_, ap) -> rssi(p, ap, noise, rnd) }

    private fun gaussian(rnd: Random): Double =
        Math.sqrt(-2.0 * Math.log(max(rnd.nextDouble(), 1e-12))) * cos(2.0 * Math.PI * rnd.nextDouble())

    private val survey: FingerprintMap by lazy {
        val rnd = Random(1)
        val pts = ArrayList<Fingerprint>()
        var x = 1.0
        while (x <= 19.0) {
            var y = 1.0
            while (y <= 9.0) {
                val p = Pt(x, y)
                // Survey readings are averaged over several samples, so they are less noisy than live ones.
                val avg = aps.keys.associateWith { id ->
                    (1..5).map { rssi(p, aps.getValue(id), 4.0, rnd) }.average().roundToInt()
                }
                pts += Fingerprint(p, avg)
                y += 2.0
            }
            x += 2.0
        }
        FingerprintMap(pts)
    }

    @Test fun `a device standing still is placed within a few metres`() {
        val rnd = Random(7)
        val truth = Pt(5.0, 4.0)
        val pf = ParticleFilter(plan, survey, random = Random(11))
        repeat(40) { pf.observe(scanAt(truth, 4.0, rnd)) }
        val err = distance(pf.estimate().at, truth)
        println("stationary error = %.2f m (spread %.2f m)".format(err, pf.estimate().spreadM))
        assertTrue("stationary error was $err m", err < 3.0)
    }

    @Test fun `a walking device is tracked to within about two metres`() {
        val rnd = Random(3)
        val pf = ParticleFilter(plan, survey, random = Random(5))
        // Walk a loop inside the west room: east along y=3, north along x=8, west along y=6, south along x=2.
        val loop = listOf(Pt(2.0, 3.0), Pt(8.0, 3.0), Pt(8.0, 6.0), Pt(2.0, 6.0))
        val corners = loop + loop + loop + loop[0]
        var pos = corners[0]
        val errors = ArrayList<Double>()
        var stepIndex = 0
        for (target in corners.drop(1)) {
            val heading = atan2(target.y - pos.y, target.x - pos.x)
            while (distance(pos, target) > 0.4) {
                pos = Pt(pos.x + 0.7 * cos(heading), pos.y + 0.7 * sin(heading))
                // The sensors report a slightly biased, noisy heading (a real compass near metal is worse).
                pf.step(0.7, heading + 0.05 + 0.08 * gaussian(rnd))
                pf.observe(scanAt(pos, 4.0, rnd))
                stepIndex++
                if (stepIndex > 15) errors += distance(pf.estimate().at, pos)
            }
        }
        val mean = errors.average()
        println("walking mean error = %.2f m over %d steps".format(mean, errors.size))
        assertTrue("walking mean error was $mean m", mean < 2.0)
    }

    @Test fun `steps cannot carry the estimate through a wall`() {
        val rnd = Random(9)
        val pf = ParticleFilter(plan, survey, random = Random(2))
        val start = Pt(8.0, 3.0)
        repeat(25) { pf.observe(scanAt(start, 4.0, rnd)) }
        // The step sensor insists the device keeps walking east, into the wall at x = 10, while it really stays put
        // (its Wi-Fi scans keep saying so).
        repeat(12) { pf.step(0.7, 0.0); pf.observe(scanAt(start, 4.0, rnd)) }
        val est = pf.estimate().at
        println("after walking into the wall: x = %.2f".format(est.x))
        assertTrue("estimate went through the wall: x = ${est.x}", est.x < 10.3)
    }

    @Test fun `a wall blocks a straight move and a doorway does not`() {
        assertTrue(!plan.canMove(Pt(9.0, 3.0), Pt(11.0, 3.0)))
        assertTrue(plan.canMove(Pt(9.0, 8.0), Pt(11.0, 8.0)))
        assertTrue(!plan.canMove(Pt(19.5, 5.0), Pt(20.5, 5.0)))
    }
}
