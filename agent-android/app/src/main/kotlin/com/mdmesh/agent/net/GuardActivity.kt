package com.mdmesh.agent.net

import android.graphics.Color
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat

/**
 * Shared shell for the two full-screen connectivity screens: edge to edge, no system bars, kept on over the lock screen,
 * pinned in lock-task mode when the device allows it, and back/home do nothing.
 */
abstract class GuardActivity : ComponentActivity() {
    protected val ui = Handler(Looper.getMainLooper())
    protected lateinit var column: LinearLayout
    protected abstract val backgroundColor: Int
    protected abstract fun onTick()
    protected abstract fun markVisible(v: Boolean)

    private val ticker = object : Runnable {
        override fun run() {
            onTick()
            ui.postDelayed(this, 1000L)
        }
    }

    protected fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(backgroundColor)
            setPadding(dp(40), dp(40), dp(40), dp(40))
            layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        }
        setContentView(column)
    }

    override fun onResume() {
        super.onResume()
        markVisible(true)
        hideBars()
        runCatching { startLockTask() }
        ui.removeCallbacks(ticker)
        ui.post(ticker)
    }

    override fun onPause() {
        markVisible(false)
        ui.removeCallbacks(ticker)
        super.onPause()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideBars()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        // Deliberately nothing: this screen cannot be dismissed with Back.
    }

    private fun hideBars() {
        val c = WindowInsetsControllerCompat(window, window.decorView)
        c.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        c.hide(WindowInsetsCompat.Type.systemBars())
    }

    protected fun text(value: String, sizeSp: Float, color: Int = Color.WHITE, bold: Boolean = false, topDp: Int = 0): TextView =
        TextView(this).apply {
            text = value
            textSize = sizeSp
            setTextColor(color)
            gravity = Gravity.CENTER
            if (bold) setTypeface(typeface, Typeface.BOLD)
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(topDp) }
        }

    protected fun minutesOffline(): Long = GuardUi.offlineSince?.let { ((System.currentTimeMillis() - it) / 60_000).coerceAtLeast(0) } ?: 0

    @Suppress("unused")
    protected fun show(v: View, visible: Boolean) { v.visibility = if (visible) View.VISIBLE else View.GONE }
}
