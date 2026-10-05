package com.mdmesh.core.net

/**
 * The hours the shop is closed ("quiet hours"), as minutes after midnight on the device's own clock. While it is quiet and
 * the tablet is sitting still, the offline guard does not count time without internet, so a router switched off overnight
 * does not block or lock the tablets by morning. See [ConnectivityPolicy].
 *
 * The setting is a string delivered from the console: `HH:MM-HH:MM` (for example `22:00-08:00`, which wraps past midnight),
 * `off` to disable the quiet window, or empty/absent for the [DEFAULT].
 */
data class QuietHours(val startMin: Int, val endMin: Int) {

    fun contains(minuteOfDay: Int): Boolean =
        if (startMin <= endMin) minuteOfDay in startMin until endMin else minuteOfDay >= startMin || minuteOfDay < endMin

    companion object {
        const val DEFAULT = "22:00-08:00"
        const val OFF = "off"
        private val FORMAT = Regex("""^([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)$""")

        /** Null means "no quiet window" (disabled). An unreadable value falls back to the default rather than switching protection off. */
        fun parse(raw: String?): QuietHours? {
            val v = raw?.trim().orEmpty()
            if (v.equals(OFF, ignoreCase = true)) return null
            val m = FORMAT.matchEntire(v) ?: FORMAT.matchEntire(DEFAULT)!!
            val (a, b, c, d) = m.destructured
            return QuietHours(a.toInt() * 60 + b.toInt(), c.toInt() * 60 + d.toInt())
        }
    }
}

/** Recent "the device was carried" signals from the motion sensor, so a tablet taken out of the shop at night is still guarded. */
object MotionState {
    private const val WINDOW_MS = 10 * 60_000L
    private const val NEEDED = 2
    private val stamps = ArrayDeque<Long>()

    @Synchronized
    fun record(now: Long = System.currentTimeMillis()) {
        stamps.addLast(now)
        while (stamps.size > 16) stamps.removeFirst()
    }

    /** True when the device has been moved repeatedly in the last ten minutes (picked up and carried, not nudged once). */
    @Synchronized
    fun sustained(now: Long = System.currentTimeMillis()): Boolean = stamps.count { now - it <= WINDOW_MS } >= NEEDED
}
