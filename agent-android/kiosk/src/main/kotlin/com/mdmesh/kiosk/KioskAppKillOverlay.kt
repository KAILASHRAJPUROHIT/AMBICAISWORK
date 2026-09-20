package com.mdmesh.kiosk

import android.content.Context
import android.graphics.Color
import android.graphics.PixelFormat
import android.os.Build
import android.provider.Settings
import android.view.Gravity
import android.view.WindowManager
import android.widget.TextView

/**
 * Small always-on-top button shown while a single pinned app is running in kiosk mode, letting
 * staff force-stop + relaunch THAT app on the spot -- no admin PIN, no exiting kiosk -- when it's
 * frozen or misbehaving. Distinct from [KioskEscapeOverlay] (a full-screen escape-detection cover)
 * and from the admin-menu kebab (PIN-gated, covers much more than one app's kill switch): this is
 * a narrow, ungated, single-purpose self-service control, deliberately small so it never blocks
 * the pinned app's own UI.
 *
 * Same `SYSTEM_ALERT_WINDOW` permission as [KioskEscapeOverlay] (already requested/granted for
 * that feature on every device using kiosk mode) -- silent no-op if it isn't granted, same
 * graceful-degrade convention used throughout this codebase.
 */
object KioskAppKillOverlay {
    private var view: TextView? = null
    private var windowManager: WindowManager? = null

    /** [onKill] is invoked on tap; the caller (KioskLauncherActivity, which owns DevicePolicyManager
     *  access) is responsible for actually suspending/relaunching the app -- this object only owns
     *  the floating button's lifecycle.
     *
     *  Re-targetable (2026-09-20, grid/multi-app mode follow-up): production kiosks run the
     *  multi-app grid, not single-pin mode -- staff open a DIFFERENT app from the grid each time,
     *  so this must retarget to whichever app is now in the foreground, not just show once and
     *  freeze on the first app ever launched. If the button already exists, only its click target
     *  is swapped; the window itself isn't recreated. */
    fun show(context: Context, onKill: () -> Unit) {
        view?.let { it.setOnClickListener { _ -> onKill() }; return }
        if (!Settings.canDrawOverlays(context)) return
        val appContext = context.applicationContext
        val wm = appContext.getSystemService(Context.WINDOW_SERVICE) as? WindowManager ?: return

        val overlayType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_SYSTEM_ALERT
        }
        // WRAP_CONTENT + a corner gravity, NOT MATCH_PARENT: this must never intercept touches
        // anywhere except its own small button, so the pinned app underneath stays fully usable.
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            overlayType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.END
            x = dp(appContext, 12)
            y = dp(appContext, 12)
        }
        val button = TextView(appContext).apply {
            text = "⟳" // ⟳ relaunch glyph
            textSize = 20f
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.argb(140, 0, 0, 0))
            val pad = dp(appContext, 10)
            setPadding(pad, pad, pad, pad)
            setOnClickListener { onKill() }
        }
        runCatching {
            wm.addView(button, params)
            view = button
            windowManager = wm
        }
    }

    fun hide() {
        val v = view ?: return
        runCatching { windowManager?.removeView(v) }
        view = null
        windowManager = null
    }

    private fun dp(context: Context, value: Int): Int =
        (value * context.resources.displayMetrics.density).toInt()
}
