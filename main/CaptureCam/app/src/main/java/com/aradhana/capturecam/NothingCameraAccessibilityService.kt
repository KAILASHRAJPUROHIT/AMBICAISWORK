package com.aradhana.capturecam

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.graphics.Point
import android.graphics.Rect
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.util.Log

/**
 * Drives Nothing Camera's own UI via its Accessibility node tree, so
 * capture can use the phone's real, proven camera pipeline (autofocus,
 * auto-exposure, and its 3.5x periscope "telemacro assist" lens) instead of
 * this app's own CameraX/zoom-climb/physical-camera-pinning logic --
 * confirmed live (2026-08-21) to visibly outperform it on fine engraved
 * detail on the exact same ring/stand/lighting. CaptureCam keeps owning
 * gimbal positioning, tag scanning, and upload; this service ONLY taps
 * Nothing Camera's own shutter and zoom controls.
 *
 * Scoped to com.nothing.camera ONLY (see nothing_camera_accessibility_config.xml's
 * android:packageNames) -- this service must never inspect or act on any
 * other app's screen content, on this or any other device it might run on.
 *
 * Node resource-ids below were confirmed live via `adb shell uiautomator
 * dump` against Nothing Camera on this exact phone (2026-08-21):
 *   com.nothing.camera:id/photo_shutter_button_photo  (content-desc "Take Photo")
 *   com.nothing.camera:id/zoom_indicator_text_view     (one node per preset, e.g. text "3.5")
 * These are ordinary app resource-ids, not part of any public API contract --
 * they can change on any Nothing Camera update with no warning. If this
 * service stops finding them, that's the first thing to re-check with a
 * fresh uiautomator dump, not a bug in this file.
 */
class NothingCameraAccessibilityService : AccessibilityService() {

    companion object {
        private const val TAG = "NothingCameraBridge"
        const val PACKAGE_NAME = "com.nothing.camera"
        private const val SHUTTER_RESOURCE_ID = "com.nothing.camera:id/photo_shutter_button_photo"
        private const val ZOOM_RESOURCE_ID = "com.nothing.camera:id/zoom_indicator_text_view"
        private const val PREVIEW_RESOURCE_ID = "com.nothing.camera:id/camera_preview_surface"
        private const val TAP_DURATION_MS = 60L

        // Set by the running service instance so MainActivity can reach it
        // without a bound-service/Messenger round trip -- this service and
        // MainActivity always run in the same process, so a plain static
        // reference is safe here (cleared in onDestroy/onUnbind).
        @Volatile
        var instance: NothingCameraAccessibilityService? = null
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        Log.i(TAG, "Connected")
    }

    override fun onUnbind(intent: android.content.Intent?): Boolean {
        instance = null
        return super.onUnbind(intent)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // No event-driven logic needed -- MainActivity polls
        // isShutterReady()/tapShutter()/setZoom() on its own schedule after
        // launching Nothing Camera. The config's typeWindowStateChanged/
        // typeWindowContentChanged registration is enough to keep the node
        // tree live and canRetrieveWindowContent working; we don't need to
        // react to individual events here.
    }

    override fun onInterrupt() {
        Log.w(TAG, "Interrupted")
    }

    /** True once Nothing Camera's photo shutter button is present in the
     * live window content -- the signal MainActivity polls for after
     * launching the app, instead of a fixed guessed delay. */
    fun isShutterReady(): Boolean = findNodeByResourceId(SHUTTER_RESOURCE_ID) != null

    /** Screen-space center of the HIGHEST zoom preset currently visible in
     * the zoom indicator row (e.g. "7" when the row shows 0.6/1/2/3.5/7),
     * paired with that preset's numeric value -- confirmed live
     * (2026-08-23 uiautomator dump) that these preset TextViews report
     * clickable="false", so ACTION_CLICK on them is not a reliable way to
     * select one; dispatchTap() below sends a real synthetic touch instead,
     * which works regardless of the node's reported clickable flag. Returns
     * null if the row can't be read right now. */
    fun maxZoomPresetCenter(): Pair<Float, Point>? {
        val root = rootInActiveWindow ?: return null
        val nodes = root.findAccessibilityNodeInfosByViewId(ZOOM_RESOURCE_ID) ?: return null
        var best: Pair<Float, Point>? = null
        for (node in nodes) {
            val value = node.text?.toString()?.trim()?.trimEnd('x', 'X', '×')?.toFloatOrNull()
            if (value != null && (best == null || value > best!!.first)) {
                val bounds = Rect()
                node.getBoundsInScreen(bounds)
                best = value to Point(bounds.centerX(), bounds.centerY())
            }
            node.recycle()
        }
        return best
    }

    /** Screen-space center of the live camera preview -- used as a
     * tap-to-focus point right before the shutter tap, since Nothing
     * Camera's autofocus needs to re-lock after a zoom-level change and
     * capturing before it does is a direct cause of soft/blurry results. */
    fun previewCenter(): Point? {
        val root = rootInActiveWindow ?: return null
        val nodes = root.findAccessibilityNodeInfosByViewId(PREVIEW_RESOURCE_ID) ?: return null
        val node = nodes.firstOrNull() ?: return null
        val bounds = Rect()
        node.getBoundsInScreen(bounds)
        node.recycle()
        return Point(bounds.centerX(), bounds.centerY())
    }

    /** Dispatches a real synthetic single-finger tap at the given screen
     * coordinates via the accessibility gesture API -- unlike
     * performAction(ACTION_CLICK), this works on views that only handle raw
     * touch events (no registered click listener/clickable=false), which is
     * how Nothing Camera's zoom presets and preview surface behave. */
    fun dispatchTap(x: Int, y: Int, onComplete: (Boolean) -> Unit) {
        val path = Path().apply { moveTo(x.toFloat(), y.toFloat()) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, TAP_DURATION_MS))
            .build()
        val dispatched = dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) {
                onComplete(true)
            }
            override fun onCancelled(gestureDescription: GestureDescription?) {
                onComplete(false)
            }
        }, null)
        if (!dispatched) onComplete(false)
    }

    /** Taps Nothing Camera's shutter via ACTION_CLICK on the node itself --
     * more reliable than a synthetic coordinate tap/dispatchGesture, since
     * it invokes the click listener directly regardless of what's currently
     * drawn on screen at that pixel position (animations, transient
     * overlays, etc. can't cause a mis-tap this way). */
    fun tapShutter(): Boolean {
        val node = findNodeByResourceId(SHUTTER_RESOURCE_ID) ?: return false
        val clicked = node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        node.recycle()
        return clicked
    }

    private fun findNodeByResourceId(resourceId: String): AccessibilityNodeInfo? {
        val root = rootInActiveWindow ?: return null
        val nodes = root.findAccessibilityNodeInfosByViewId(resourceId) ?: return null
        return nodes.firstOrNull()
    }
}
