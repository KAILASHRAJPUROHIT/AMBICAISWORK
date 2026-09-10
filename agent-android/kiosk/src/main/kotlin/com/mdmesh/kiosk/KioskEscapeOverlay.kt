package com.mdmesh.kiosk

import android.content.Context
import android.graphics.Color
import android.graphics.PixelFormat
import android.os.Build
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.TextView

/**
 * Full-screen overlay shown the instant [KioskWatchdogService] detects a lock-task escape, to
 * cover the home/recents screen during the brief window before the pinned app is relaunched and
 * re-pinned. [SoftPinKioskController]'s doc comment already discloses that the underlying
 * Back+Recents unpin gesture itself cannot be blocked — this closes the *practical* gap instead:
 * what the user sees and can tap during that window is this overlay, not the home screen or its
 * other apps.
 *
 * Requires `SYSTEM_ALERT_WINDOW` ([com.mdmesh.core.permission.OverlayPermission]) — [show] is a
 * silent no-op if it isn't granted, same graceful-degrade convention as every other
 * permission-gated feature in this codebase; the watchdog's relaunch-only behavior still works
 * without it.
 */
object KioskEscapeOverlay {
    private var view: View? = null
    private var windowManager: WindowManager? = null

    fun show(context: Context) {
        if (view != null) return
        if (!Settings.canDrawOverlays(context)) return
        val appContext = context.applicationContext
        val wm = appContext.getSystemService(Context.WINDOW_SERVICE) as? WindowManager ?: return

        val overlayType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_SYSTEM_ALERT
        }
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            overlayType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.OPAQUE,
        )
        val container = FrameLayout(appContext).apply {
            setBackgroundColor(Color.parseColor("#0E1117"))
            addView(
                TextView(appContext).apply {
                    text = "Device locked"
                    setTextColor(Color.parseColor("#E8EEF4"))
                    textSize = 22f
                    gravity = Gravity.CENTER
                },
                FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT,
                    FrameLayout.LayoutParams.MATCH_PARENT,
                    Gravity.CENTER,
                ),
            )
        }
        runCatching {
            wm.addView(container, params)
            view = container
            windowManager = wm
        }
    }

    fun hide() {
        val v = view ?: return
        runCatching { windowManager?.removeView(v) }
        view = null
        windowManager = null
    }
}
