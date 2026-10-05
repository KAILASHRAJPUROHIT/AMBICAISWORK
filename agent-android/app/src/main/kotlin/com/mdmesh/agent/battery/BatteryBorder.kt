package com.mdmesh.agent.battery

import android.app.Activity
import android.app.Application
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import com.mdmesh.core.battery.BatteryStage
import com.mdmesh.core.battery.BatteryUi
import java.lang.ref.WeakReference

/** Stage colours shared by the screen border, the battery pill and the warning banner. */
object BatteryColors {
    val yellow = Color.parseColor("#F2C230")
    val orange = Color.parseColor("#F28C28")
    val red = Color.parseColor("#E5484D")

    fun of(stage: BatteryStage): Int? = when (stage) {
        BatteryStage.NORMAL -> null
        BatteryStage.YELLOW -> yellow
        BatteryStage.ORANGE -> orange
        BatteryStage.RED -> red
    }
}

/**
 * Draws a coloured frame around the whole screen of every MDM activity while the battery is in a warning stage: yellow at
 * 21 to 30%, orange at 11 to 20%, red at 10% and below. It is a foreground drawable on the window's decor view, so it sits
 * above everything and needs no change in any individual screen. It disappears when the tablet is charging.
 */
object BatteryBorder : Application.ActivityLifecycleCallbacks {
    private val main = Handler(Looper.getMainLooper())
    private var resumed: WeakReference<Activity>? = null
    private val onChange: () -> Unit = { main.post { resumed?.get()?.let { apply(it) } } }

    fun install(app: Application) {
        app.registerActivityLifecycleCallbacks(this)
        BatteryUi.addListener(onChange)
    }

    private fun apply(activity: Activity) {
        val color = BatteryColors.of(BatteryUi.stage)
        val decor = activity.window?.decorView ?: return
        decor.foreground = color?.let {
            val px = (BORDER_DP * activity.resources.displayMetrics.density).toInt().coerceAtLeast(4)
            GradientDrawable().apply { setColor(Color.TRANSPARENT); setStroke(px, it) }
        }
    }

    override fun onActivityResumed(activity: Activity) {
        resumed = WeakReference(activity)
        // A screen that has just opened reads the battery itself, so it is never a stale colour.
        BatteryUi.refreshFrom(activity)
        apply(activity)
    }

    override fun onActivityPaused(activity: Activity) { if (resumed?.get() === activity) resumed = null }
    override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) = Unit
    override fun onActivityStarted(activity: Activity) = Unit
    override fun onActivityStopped(activity: Activity) = Unit
    override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) = Unit
    override fun onActivityDestroyed(activity: Activity) = Unit

    private const val BORDER_DP = 7
}
