package com.mdmesh.core.battery

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import java.util.concurrent.CopyOnWriteArrayList

/** How worried the screens and the voice are about the battery. */
enum class BatteryStage { NORMAL, YELLOW, ORANGE, RED }

/**
 * Battery warning rules (one place, unit tested):
 *  - 31% and above, or charging: [BatteryStage.NORMAL]
 *  - 21 to 30%: [BatteryStage.YELLOW]
 *  - 11 to 20%: [BatteryStage.ORANGE]
 *  - 10% and below: [BatteryStage.RED]
 * A sound plays each time the stage gets worse (at 30, 20 and 10%), and keeps repeating at RED until the tablet is charging.
 */
object BatteryStagePolicy {
    const val RED_REPEAT_MS = 2 * 60_000L

    fun stageOf(percent: Int, charging: Boolean): BatteryStage = when {
        charging || percent < 0 -> BatteryStage.NORMAL
        percent > 30 -> BatteryStage.NORMAL
        percent > 20 -> BatteryStage.YELLOW
        percent > 10 -> BatteryStage.ORANGE
        else -> BatteryStage.RED
    }

    /** True when going from [previous] to [now] is a drop into a warning stage. Recovery and no change never play. */
    fun shouldAnnounce(previous: BatteryStage?, now: BatteryStage): Boolean =
        previous != null && now != BatteryStage.NORMAL && now.ordinal > previous.ordinal
}

/** Latest battery reading and stage, shared by the sound controller and every screen that draws the coloured border. */
object BatteryUi {
    @Volatile var percent: Int = -1
        private set
    @Volatile var charging: Boolean = false
        private set
    @Volatile var stage: BatteryStage = BatteryStage.NORMAL
        private set

    private val listeners = CopyOnWriteArrayList<() -> Unit>()

    fun addListener(l: () -> Unit) { listeners.addIfAbsent(l) }
    fun removeListener(l: () -> Unit) { listeners.remove(l) }

    /** Records a reading and tells the listeners when the stage changed. Returns the previous stage. */
    fun update(percent: Int, charging: Boolean): BatteryStage {
        val previous = stage
        this.percent = percent
        this.charging = charging
        stage = BatteryStagePolicy.stageOf(percent, charging)
        listeners.forEach { runCatching { it() } }
        return previous
    }

    /** Reads the battery straight from the system (sticky broadcast) so a screen that has just opened is never out of date. */
    fun refreshFrom(context: Context): BatteryStage {
        val i: Intent? = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = i?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = i?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        val status = i?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val pct = if (level >= 0 && scale > 0) level * 100 / scale else -1
        val charging = status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL
        return update(pct, charging)
    }
}
