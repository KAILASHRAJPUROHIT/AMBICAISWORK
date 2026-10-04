package com.mdmesh.core.indoor

import com.mdmesh.proto.IndoorBundleDto
import com.mdmesh.proto.IndoorFixDto
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

/**
 * On-device in-store positioning. Holds the downloaded plan + survey, runs the [ParticleFilter] on it, and exposes the
 * latest position estimate for telemetry. Fed by step events ([onStep]) and Wi-Fi scans ([observe]).
 *
 * All filter access is serialised on [lock]; callers may use it from the sensor thread and from coroutines.
 */
@Singleton
class IndoorEngine @Inject constructor(
    private val repository: IndoorRepository,
    private val wifi: WifiScanner,
    private val magnetic: MagneticReader,
) {
    private val lock = Any()
    private var bundle: IndoorBundleDto? = null
    private var filter: ParticleFilter? = null
    @Volatile private var lastFix: IndoorFixDto? = null

    /** True once a plan is loaded (from the cache or the server). */
    fun hasMap(): Boolean = synchronized(lock) { ensureFromCache(); bundle != null }

    /** Compass-to-plan conversion needs the plan's north offset. */
    fun northDeg(): Double = synchronized(lock) { bundle?.plan?.northDeg ?: 0.0 }

    /** Fetches the latest plan + survey from the server and rebuilds the filter if it changed. */
    suspend fun reload(): Boolean {
        val fresh = repository.refresh()
        synchronized(lock) { install(fresh) }
        return fresh != null
    }

    /** One detected step of [lengthM] metres along a compass [bearingDeg] (clockwise from north). */
    fun onStep(lengthM: Double, bearingDeg: Double) {
        synchronized(lock) {
            ensureFromCache()
            val f = filter ?: return
            val b = bundle ?: return
            f.step(lengthM, IndoorGeometry.planHeadingRad(bearingDeg, b.plan.northDeg))
            publish(f, b)
        }
    }

    /** Correct the estimate with a Wi-Fi scan (BSSID -> dBm) and, if known, the magnetic field strength in µT. */
    fun observe(scan: Map<String, Int>, magneticUt: Double? = null) {
        synchronized(lock) {
            ensureFromCache()
            val f = filter ?: return
            val b = bundle ?: return
            f.observe(scan, magneticUt)
            publish(f, b)
        }
    }

    /** The newest estimate, or null when there is none or it is older than [maxAgeMs]. */
    fun fix(maxAgeMs: Long): IndoorFixDto? =
        lastFix?.takeIf { System.currentTimeMillis() - it.at <= maxAgeMs }

    /**
     * "Locate in store": scan Wi-Fi a few times and return the resulting estimate. A device that has been idle for a
     * while starts from scratch, because the walking history no longer says anything about where it is.
     */
    suspend fun locateNow(): IndoorFixDto? = withContext(Dispatchers.IO) {
        if (!hasMap()) reload()
        if (!hasMap()) return@withContext null
        val stale = lastFix?.let { System.currentTimeMillis() - it.at > STALE_FIX_MS } ?: true
        if (stale) synchronized(lock) { filter?.scatter() }
        val mag = magnetic.read()
        val scans = ArrayList<Map<String, Int>>()
        scans += wifi.latest()
        scans += wifi.scan(SCAN_WAIT_MS)
        delay(1_500)
        scans += wifi.scan(SCAN_WAIT_MS)
        for (s in scans.filter { it.isNotEmpty() }.distinct()) observe(s, mag)
        lastFix
    }

    /**
     * Records a survey point at plan position ([x], [y]): averages [samples] Wi-Fi scans, adds the magnetic field and
     * uploads it. Returns null on success or the reason it failed.
     */
    suspend fun survey(x: Double, y: Double, samples: Int): String? = withContext(Dispatchers.IO) {
        val scans = ArrayList<Map<String, Int>>()
        repeat(samples.coerceIn(1, 5)) { i ->
            if (i > 0) delay(SURVEY_GAP_MS)
            val s = wifi.scan(SCAN_WAIT_MS)
            if (s.isNotEmpty()) scans += s
        }
        if (scans.isEmpty()) return@withContext "no Wi-Fi networks heard here; check that Wi-Fi and location are on"
        val reading = WifiScanner.average(scans)
        val err = repository.uploadSurvey(x, y, reading, magnetic.read())
        if (err == null) reload()
        err
    }

    private fun ensureFromCache() {
        if (bundle == null) install(repository.cached())
    }

    private fun install(fresh: IndoorBundleDto?) {
        if (fresh == null) { bundle = null; filter = null; lastFix = null; return }
        if (fresh.updatedAt == bundle?.updatedAt && fresh.points.size == bundle?.points?.size && filter != null) return
        bundle = fresh
        filter = ParticleFilter(IndoorGeometry.floorPlan(fresh.plan), IndoorGeometry.fingerprintMap(fresh))
    }

    private fun publish(f: ParticleFilter, b: IndoorBundleDto) {
        val e = f.estimate()
        lastFix = IndoorFixDto(
            x = e.at.x,
            y = e.at.y,
            spreadM = e.spreadM,
            zone = IndoorGeometry.zoneAt(b.plan, e.at.x, e.at.y),
            at = System.currentTimeMillis(),
        )
    }

    private companion object {
        const val STALE_FIX_MS = 2 * 60_000L
        const val SCAN_WAIT_MS = 8_000L
        const val SURVEY_GAP_MS = 10_000L
    }
}
