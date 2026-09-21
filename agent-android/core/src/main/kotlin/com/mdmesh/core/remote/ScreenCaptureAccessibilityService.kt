package com.mdmesh.core.remote

import android.accessibilityservice.AccessibilityService
import android.graphics.Bitmap
import android.os.Build
import android.view.accessibility.AccessibilityEvent
import androidx.annotation.RequiresApi
import java.io.ByteArrayOutputStream
import kotlin.coroutines.resume
import kotlin.coroutines.suspendCoroutine

/**
 * Exists solely for [takeScreenshot] (API 30+) — the one silent way to capture the screen for a
 * remote-view session (see [com.mdmesh.core.permission.ScreenCaptureAccessibilityPermission] for
 * why this needs a one-time manual enable, and why that's still the better trade-off than
 * MediaProjection's every-session consent dialog). Deliberately does nothing else: no
 * [onAccessibilityEvent] handling, matching this codebase's existing precedent
 * (`com.mdmesh.remote.InputInjectionService`'s "it injects, it does not snoop") of keeping each
 * accessibility service scoped to exactly the one capability it exists for.
 */
class ScreenCaptureAccessibilityService : AccessibilityService() {

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent) {}
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

        /** Inject global navigation key actions (back, home, recents, notifications, lock). */
        fun injectKey(key: String): Boolean {
            val svc = instance ?: return false
            return when (key.lowercase()) {
                "back" -> svc.performGlobalAction(GLOBAL_ACTION_BACK)
                "home" -> svc.performGlobalAction(GLOBAL_ACTION_HOME)
                "recents" -> svc.performGlobalAction(GLOBAL_ACTION_RECENTS)
                "notifications" -> svc.performGlobalAction(GLOBAL_ACTION_NOTIFICATIONS)
                "lock" -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    svc.performGlobalAction(GLOBAL_ACTION_LOCK_SCREEN)
                } else false
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
