package com.aradhana.capturecam

import android.accessibilityservice.AccessibilityService
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

    /** Taps the given zoom preset (e.g. "3.5") if that exact preset is
     * currently visible in the zoom indicator row. Returns false (does
     * nothing) if it isn't found -- callers should treat that as "zoom
     * unavailable right now", not retry-forever, since the row's visible
     * presets can change with camera state. */
    fun setZoom(label: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val nodes = root.findAccessibilityNodeInfosByViewId(ZOOM_RESOURCE_ID) ?: return false
        for (node in nodes) {
            if (node.text?.toString()?.trim()?.trimEnd('x', 'X', '×') == label) {
                val clicked = node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                node.recycle()
                return clicked
            }
            node.recycle()
        }
        return false
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
