package com.mdmesh.core.remote

import android.accessibilityservice.AccessibilityService
import android.graphics.Bitmap
import android.os.Build
import android.view.accessibility.AccessibilityEvent
import androidx.annotation.RequiresApi
import java.io.ByteArrayOutputStream
import kotlin.coroutines.resume
import kotlin.coroutines.suspendCoroutine

import android.os.Bundle
import android.util.Log
import android.view.accessibility.AccessibilityNodeInfo

/**
 * Exists for [takeScreenshot] (API 30+) remote-view sessions, input injection, and
 * auto-uppercase text enforcement for enterprise apps (e.g. Ornate Buddy).
 */
class ScreenCaptureAccessibilityService : AccessibilityService() {

    @Volatile private var transformingUntilMs = 0L

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        Log.i("ScreenCaptureA11y", "ScreenCaptureAccessibilityService connected")
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
        Log.i("ScreenCaptureA11y", "ScreenCaptureAccessibilityService destroyed")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        try {
            handleAccessibilityEvent(event)
        } catch (t: Throwable) {
            Log.e("ScreenCaptureA11y", "Crash prevented in onAccessibilityEvent", t)
        }
    }

    private fun handleAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null || event.eventType != AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED) return
        val pkg = event.packageName?.toString() ?: return
        if (pkg != "com.ornate.nx") return

        // 1. Timed re-entrancy lock: ignore events triggered by our own transformations.
        // Automatically expires so a stalled operation never permanently halts auto-caps.
        if (System.currentTimeMillis() < transformingUntilMs) return

        // 2. NEVER intervene on deletions, backspaces, cuts, or clears!
        // When text is deleted or cleared, addedCount is 0. Intervening during deletion disrupts the
        // keyboard's composing state and triggers Ornate's data-watcher to re-fill deleted prefilled text.
        if (event.addedCount <= 0) return

        val source = event.source ?: return

        // 3. Focus check: only transform if the view is actively focused or being edited by the user.
        // When Ornate opens a screen and prefills customer name, invoice info, etc. in the background,
        // the view is NOT focused. Intervening on unfocused views corrupts Ornate's prefilled data.
        val hasFocus = source.isFocused || source.isAccessibilityFocused
        if (!hasFocus) {
            val root = rootInActiveWindow
            val activeInput = root?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
            val isCurrentInput = activeInput != null && activeInput == source
            if (!isCurrentInput) return
        }

        // 4. Exclude password inputs
        if (source.isPassword) return

        // 5. Exclude Login / Server settings fields (usernames/passwords/IPs are often lowercase)
        val viewId = runCatching { source.viewIdResourceName?.lowercase() }.getOrNull()
        if (viewId != null) {
            if (viewId.contains("username") || viewId.contains("password") ||
                viewId.contains("login") || viewId.contains("server") ||
                viewId.contains("ip") || viewId.contains("port")) {
                return
            }
        }

        val currentText = runCatching { source.text?.toString() }.getOrNull() ?: return
        if (currentText.isEmpty()) return

        // 6. Only transform if there is at least one lowercase character to convert
        val hasLower = currentText.any { it.isLowerCase() }
        if (!hasLower) return

        val upper = currentText.uppercase()
        if (upper == currentText) return

        // Lock for 300ms while setting text so self-triggered text changes are ignored
        transformingUntilMs = System.currentTimeMillis() + 300L
        try {
            val selStart = runCatching { source.textSelectionStart }.getOrDefault(-1)
            val selEnd = runCatching { source.textSelectionEnd }.getOrDefault(-1)

            val arguments = Bundle().apply {
                putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, upper)
            }
            val ok = source.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)
            if (ok) {
                val targetStart = if (selStart in 0..upper.length) selStart else upper.length
                val targetEnd = if (selEnd in targetStart..upper.length) selEnd else targetStart
                val selArgs = Bundle().apply {
                    putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, targetStart)
                    putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, targetEnd)
                }
                source.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, selArgs)
            }
        } catch (t: Throwable) {
            Log.w("ScreenCaptureA11y", "Auto-caps setText error", t)
        }
    }

    override fun onInterrupt() {}

    companion object {
        @Volatile private var instance: ScreenCaptureAccessibilityService? = null

        fun isConnected(): Boolean = instance != null

        /** JPEG bytes of the current default-display screenshot, or null if the service isn't
         *  bound (not enabled in Settings) or the platform is too old / the capture failed. */
        @RequiresApi(Build.VERSION_CODES.R)
        suspend fun captureJpeg(quality: Int = 70): ByteArray? {
            val svc = instance ?: return null
            val bitmap = svc.takeScreenshotSuspend() ?: return null
            return ByteArrayOutputStream().use { out ->
                bitmap.compress(Bitmap.CompressFormat.JPEG, quality, out)
                bitmap.recycle()
                out.toByteArray()
            }
        }

        /** Inject a tap gesture at relative coordinates (0.0 to 1.0). */
        fun injectTap(xRatio: Float, yRatio: Float): Boolean {
            val svc = instance ?: return false
            val dm = svc.resources.displayMetrics
            val x = (xRatio * dm.widthPixels).coerceIn(0f, dm.widthPixels.toFloat())
            val y = (yRatio * dm.heightPixels).coerceIn(0f, dm.heightPixels.toFloat())
            val path = android.graphics.Path().apply { moveTo(x, y) }
            val stroke = android.accessibilityservice.GestureDescription.StrokeDescription(path, 0, 50)
            val gesture = android.accessibilityservice.GestureDescription.Builder().addStroke(stroke).build()
            return svc.dispatchGesture(gesture, null, null)
        }

        /** Inject a swipe gesture between relative coordinates (0.0 to 1.0). */
        fun injectSwipe(x1Ratio: Float, y1Ratio: Float, x2Ratio: Float, y2Ratio: Float, durationMs: Long = 300): Boolean {
            val svc = instance ?: return false
            val dm = svc.resources.displayMetrics
            val x1 = (x1Ratio * dm.widthPixels).coerceIn(0f, dm.widthPixels.toFloat())
            val y1 = (y1Ratio * dm.heightPixels).coerceIn(0f, dm.heightPixels.toFloat())
            val x2 = (x2Ratio * dm.widthPixels).coerceIn(0f, dm.widthPixels.toFloat())
            val y2 = (y2Ratio * dm.heightPixels).coerceIn(0f, dm.heightPixels.toFloat())
            val path = android.graphics.Path().apply {
                moveTo(x1, y1)
                lineTo(x2, y2)
            }
            val stroke = android.accessibilityservice.GestureDescription.StrokeDescription(path, 0, durationMs.coerceIn(50, 2000))
            val gesture = android.accessibilityservice.GestureDescription.Builder().addStroke(stroke).build()
            return svc.dispatchGesture(gesture, null, null)
        }

        /** Inject text into the currently focused input field. */
        fun injectText(text: String): Boolean {
            val svc = instance ?: return false
            val root = svc.rootInActiveWindow ?: return false
            val node = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT) ?: findEditable(root)
            if (node == null) return false
            return runCatching {
                val args = Bundle().apply {
                    putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
                }
                node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
            }.getOrDefault(false)
        }

        private fun findEditable(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
            if (node.isEditable) return node
            for (i in 0 until node.childCount) {
                val child = node.getChild(i) ?: continue
                val found = findEditable(child)
                if (found != null) return found
            }
            return null
        }

        /** Inject global navigation key actions (back, home, recents, notifications, quicksettings, power, lock, volume). */
        fun injectKey(key: String): Boolean {
            val svc = instance ?: return false
            return when (key.lowercase()) {
                "back" -> svc.performGlobalAction(GLOBAL_ACTION_BACK)
                "home" -> svc.performGlobalAction(GLOBAL_ACTION_HOME)
                "recents" -> svc.performGlobalAction(GLOBAL_ACTION_RECENTS)
                "notifications" -> svc.performGlobalAction(GLOBAL_ACTION_NOTIFICATIONS)
                "quicksettings" -> svc.performGlobalAction(GLOBAL_ACTION_QUICK_SETTINGS)
                "power" -> svc.performGlobalAction(GLOBAL_ACTION_POWER_DIALOG)
                "lock" -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    svc.performGlobalAction(GLOBAL_ACTION_LOCK_SCREEN)
                } else false
                "volume_up" -> {
                    val am = svc.getSystemService(android.content.Context.AUDIO_SERVICE) as? android.media.AudioManager
                    am?.adjustVolume(android.media.AudioManager.ADJUST_RAISE, android.media.AudioManager.FLAG_SHOW_UI)
                    true
                }
                "volume_down" -> {
                    val am = svc.getSystemService(android.content.Context.AUDIO_SERVICE) as? android.media.AudioManager
                    am?.adjustVolume(android.media.AudioManager.ADJUST_LOWER, android.media.AudioManager.FLAG_SHOW_UI)
                    true
                }
                else -> false
            }
        }
    }

    @RequiresApi(Build.VERSION_CODES.R)
    private suspend fun takeScreenshotSuspend(): Bitmap? = suspendCoroutine { cont ->
        takeScreenshot(
            android.view.Display.DEFAULT_DISPLAY,
            mainExecutor,
            object : TakeScreenshotCallback {
                override fun onSuccess(result: ScreenshotResult) {
                    val bitmap = runCatching {
                        Bitmap.wrapHardwareBuffer(result.hardwareBuffer, result.colorSpace)
                            ?.copy(Bitmap.Config.ARGB_8888, false)
                    }.getOrNull()
                    result.hardwareBuffer.close()
                    cont.resume(bitmap)
                }

                override fun onFailure(errorCode: Int) {
                    cont.resume(null)
                }
            },
        )
    }
}

private typealias TakeScreenshotCallback = AccessibilityService.TakeScreenshotCallback
private typealias ScreenshotResult = AccessibilityService.ScreenshotResult
