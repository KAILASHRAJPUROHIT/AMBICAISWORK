package com.aradhana.capturecam

import android.app.Activity
import android.content.Intent
import android.database.Cursor
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.provider.Settings
import android.util.Log

/**
 * Orchestrates one photo capture through Nothing Camera instead of this
 * app's own CameraX pipeline, via NothingCameraAccessibilityService.
 * Deliberately matches captureOneFrame/captureFullRes's exact
 * `(onResult: (ByteArray?) -> Unit)` shape (MainActivity.kt) so it's a
 * drop-in alternate capture source -- every downstream step (staging,
 * upload, tagging) is completely unchanged.
 *
 * Confirmed live (2026-08-21): the same ring/stand/lighting produced
 * visibly sharper, better-exposed engraving through Nothing Camera's own
 * pipeline than through this app's CameraX/zoom-climb logic -- this exists
 * to let capture use that real pipeline (autofocus, auto-exposure, and its
 * 3.5x periscope "telemacro assist" lens) while CaptureCam keeps owning
 * gimbal positioning, tag scanning, and upload.
 */
object NothingCameraBridge {
    private const val TAG = "NothingCameraBridge"
    private const val SHUTTER_READY_TIMEOUT_MS = 5_000L
    private const val SHUTTER_READY_POLL_MS = 150L
    private const val ZOOM_SETTLE_MS = 900L
    private const val FOCUS_SETTLE_MS = 900L
    private const val PHOTO_APPEAR_TIMEOUT_MS = 4_000L
    private const val PHOTO_APPEAR_POLL_MS = 200L

    private val handler = Handler(Looper.getMainLooper())

    /** True once the user has enabled this service in Settings ->
     * Accessibility (Android provides no API to grant this programmatically
     * -- it's a one-time manual step per device). */
    fun isServiceEnabled(activity: Activity): Boolean {
        val expected = "${activity.packageName}/${NothingCameraAccessibilityService::class.java.name}"
        val enabled = Settings.Secure.getString(
            activity.contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        ) ?: return false
        return enabled.split(':').any { it.equals(expected, ignoreCase = true) }
    }

    /** Deep-links to the Accessibility Settings screen for this service.
     * Android does not support pre-selecting the specific service on most
     * OEM builds, so this opens the general list -- MainActivity's caller
     * should tell the operator which entry to enable ("CaptureCam: Nothing
     * Camera control"), matching the manifest's android:label. */
    fun openAccessibilitySettings(activity: Activity) {
        activity.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
    }

    // Confirmed live (2026-08-23): captureJewel() is called from tickJewel(),
    // a periodic tick loop whose re-fire guard assumes a capture completes
    // quickly, the way CameraX's captureFullRes does. This bridge's sequence
    // is much slower (app launch, shutter-ready polling, zoom settle delay,
    // MediaStore polling) -- without a guard here, the tick loop kept
    // re-firing captureJewel() DURING an in-flight attempt, piling up many
    // concurrent captureViaNothingCamera() calls that all fought over the
    // same Nothing Camera UI state at once. That's what "switched to Nothing
    // Camera but immediately bounced back without capturing" actually was:
    // dozens of overlapping launch/fail cycles inside under a second, not
    // one clean attempt. A capture that's already in flight now makes every
    // new call fail open immediately instead of piling on.
    @Volatile
    private var captureInFlight = false

    /**
     * Full capture sequence: launch Nothing Camera, wait for its shutter to
     * be reachable, set telemacro zoom, tap the shutter, then read back
     * whatever it just saved. Fails open (onResult(null)) at every step
     * rather than throwing -- matching captureOneFrame's own contract, so
     * callers already handle a null result the same way a CameraX failure
     * is handled.
     */
    fun captureViaNothingCamera(activity: Activity, onResult: (ByteArray?) -> Unit) {
        if (captureInFlight) {
            Log.w(TAG, "captureViaNothingCamera called while an attempt is already in flight -- ignoring")
            onResult(null)
            return
        }
        captureInFlight = true
        val wrappedResult: (ByteArray?) -> Unit = { bytes ->
            captureInFlight = false
            onResult(bytes)
        }

        val service = NothingCameraAccessibilityService.instance
        if (service == null) {
            Log.w(TAG, "Accessibility service not connected -- is it enabled in Settings?")
            wrappedResult(null)
            return
        }

        val baselineNewestId = latestImageId(activity)

        val launchIntent = activity.packageManager
            .getLaunchIntentForPackage(NothingCameraAccessibilityService.PACKAGE_NAME)
        if (launchIntent == null) {
            Log.e(TAG, "Nothing Camera not installed/launchable")
            wrappedResult(null)
            return
        }
        launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        activity.startActivity(launchIntent)

        waitForShutterReady(startedAt = System.currentTimeMillis()) { ready ->
            if (!ready) {
                Log.w(TAG, "Nothing Camera shutter never became reachable")
                returnToCaptureCam(activity)
                wrappedResult(null)
                return@waitForShutterReady
            }

            // Best-effort: if the zoom row can't be read right now, still
            // proceed with a focus tap + shutter at whatever zoom level
            // Nothing Camera is already at, rather than failing the whole
            // capture over an optional detail step.
            val zoomTarget = service.maxZoomPresetCenter()
            if (zoomTarget == null) {
                Log.w(TAG, "No zoom presets found -- capturing at current zoom")
                focusThenShutter(activity, baselineNewestId, wrappedResult)
                return@waitForShutterReady
            }
            val (zoomValue, zoomPoint) = zoomTarget
            Log.i(TAG, "Tapping max zoom preset ${zoomValue}x at $zoomPoint")
            service.dispatchTap(zoomPoint.x, zoomPoint.y) { tapped ->
                Log.i(TAG, "Zoom tap dispatched: $tapped")
                handler.postDelayed({
                    focusThenShutter(activity, baselineNewestId, wrappedResult)
                }, ZOOM_SETTLE_MS)
            }
        }
    }

    /** Taps the live preview to force autofocus to re-lock at the current
     * zoom level, waits for it to settle, then fires the shutter. Doing
     * this unconditionally (not just on the first attempt) is what actually
     * fixes soft/blurry captures -- Nothing Camera's AF needs to refocus
     * after a zoom-level change, and firing the shutter immediately after
     * the zoom tap (the old flow) reliably beat it to the punch. */
    private fun focusThenShutter(activity: Activity, baselineNewestId: Long, wrappedResult: (ByteArray?) -> Unit) {
        val service = NothingCameraAccessibilityService.instance
        if (service == null) {
            Log.w(TAG, "Service disconnected before focus/shutter step")
            returnToCaptureCam(activity)
            wrappedResult(null)
            return
        }
        val previewPoint = service.previewCenter()
        if (previewPoint == null) {
            Log.w(TAG, "No preview node found -- skipping focus tap")
            tapShutterAndWait(activity, baselineNewestId, wrappedResult)
            return
        }
        service.dispatchTap(previewPoint.x, previewPoint.y) { tapped ->
            Log.i(TAG, "Focus tap dispatched: $tapped")
            handler.postDelayed({
                tapShutterAndWait(activity, baselineNewestId, wrappedResult)
            }, FOCUS_SETTLE_MS)
        }
    }

    private fun tapShutterAndWait(activity: Activity, baselineNewestId: Long, wrappedResult: (ByteArray?) -> Unit) {
        val service = NothingCameraAccessibilityService.instance
        val tapped = service?.tapShutter() ?: false
        if (!tapped) {
            Log.e(TAG, "Shutter tap failed")
            returnToCaptureCam(activity)
            wrappedResult(null)
            return
        }
        waitForNewPhoto(activity, baselineNewestId, startedAt = System.currentTimeMillis()) { uri ->
            returnToCaptureCam(activity)
            if (uri == null) {
                Log.e(TAG, "No new photo appeared in MediaStore after shutter tap")
                wrappedResult(null)
                return@waitForNewPhoto
            }
            val bytes = try {
                activity.contentResolver.openInputStream(uri)?.use { it.readBytes() }
            } catch (e: Exception) {
                Log.e(TAG, "Failed reading captured photo bytes", e)
                null
            }
            wrappedResult(bytes)
        }
    }

    private fun waitForShutterReady(startedAt: Long, onDone: (Boolean) -> Unit) {
        val service = NothingCameraAccessibilityService.instance
        if (service != null && service.isShutterReady()) {
            onDone(true)
            return
        }
        if (System.currentTimeMillis() - startedAt >= SHUTTER_READY_TIMEOUT_MS) {
            onDone(false)
            return
        }
        handler.postDelayed({ waitForShutterReady(startedAt, onDone) }, SHUTTER_READY_POLL_MS)
    }

    private fun waitForNewPhoto(activity: Activity, baselineId: Long, startedAt: Long, onDone: (Uri?) -> Unit) {
        val newest = latestImageRow(activity)
        if (newest != null && newest.first > baselineId) {
            onDone(ContentUris(newest.first))
            return
        }
        if (System.currentTimeMillis() - startedAt >= PHOTO_APPEAR_TIMEOUT_MS) {
            onDone(null)
            return
        }
        handler.postDelayed({ waitForNewPhoto(activity, baselineId, startedAt, onDone) }, PHOTO_APPEAR_POLL_MS)
    }

    private fun ContentUris(id: Long): Uri =
        android.content.ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id)

    private fun latestImageId(activity: Activity): Long = latestImageRow(activity)?.first ?: 0L

    /** Returns (id, dateAdded) of the most recently added row in the shared
     * image store, or null if the query fails/returns nothing -- scoped
     * storage still allows querying (not necessarily reading bytes of)
     * other apps' MediaStore rows without additional permission on most
     * API levels, but READ_MEDIA_IMAGES is requested anyway (see manifest)
     * since we DO read the bytes of the one row we identify. */
    private fun latestImageRow(activity: Activity): Pair<Long, Long>? {
        val projection = arrayOf(MediaStore.Images.Media._ID, MediaStore.Images.Media.DATE_ADDED)
        val sort = "${MediaStore.Images.Media.DATE_ADDED} DESC"
        var cursor: Cursor? = null
        return try {
            cursor = activity.contentResolver.query(
                MediaStore.Images.Media.EXTERNAL_CONTENT_URI, projection, null, null, sort
            )
            if (cursor != null && cursor.moveToFirst()) {
                val id = cursor.getLong(cursor.getColumnIndexOrThrow(MediaStore.Images.Media._ID))
                val dateAdded = cursor.getLong(cursor.getColumnIndexOrThrow(MediaStore.Images.Media.DATE_ADDED))
                id to dateAdded
            } else null
        } catch (e: Exception) {
            Log.e(TAG, "MediaStore query failed", e)
            null
        } finally {
            cursor?.close()
        }
    }

    /** Nothing Camera launched on top of us with FLAG_ACTIVITY_NEW_TASK;
     * bring CaptureCam back to the foreground now that we have (or failed
     * to get) a result, rather than leaving the operator stranded in
     * Nothing Camera. */
    private fun returnToCaptureCam(activity: Activity) {
        val intent = Intent(activity, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        activity.startActivity(intent)
    }
}
