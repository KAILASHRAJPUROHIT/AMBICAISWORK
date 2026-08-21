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
    private const val ZOOM_SETTLE_MS = 500L
    private const val PHOTO_APPEAR_TIMEOUT_MS = 4_000L
    private const val PHOTO_APPEAR_POLL_MS = 200L
    private const val TELEMACRO_ZOOM_LABEL = "3.5"

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

    /**
     * Full capture sequence: launch Nothing Camera, wait for its shutter to
     * be reachable, set telemacro zoom, tap the shutter, then read back
     * whatever it just saved. Fails open (onResult(null)) at every step
     * rather than throwing -- matching captureOneFrame's own contract, so
     * callers already handle a null result the same way a CameraX failure
     * is handled.
     */
    fun captureViaNothingCamera(activity: Activity, onResult: (ByteArray?) -> Unit) {
        val service = NothingCameraAccessibilityService.instance
        if (service == null) {
            Log.w(TAG, "Accessibility service not connected -- is it enabled in Settings?")
            onResult(null)
            return
        }

        val baselineNewestId = latestImageId(activity)

        val launchIntent = activity.packageManager
            .getLaunchIntentForPackage(NothingCameraAccessibilityService.PACKAGE_NAME)
        if (launchIntent == null) {
            Log.e(TAG, "Nothing Camera not installed/launchable")
            onResult(null)
            return
        }
        launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        activity.startActivity(launchIntent)

        waitForShutterReady(startedAt = System.currentTimeMillis()) { ready ->
            if (!ready) {
                Log.w(TAG, "Nothing Camera shutter never became reachable")
                returnToCaptureCam(activity)
                onResult(null)
                return@waitForShutterReady
            }

            // Best-effort: if the 3.5x preset isn't visible for whatever
            // reason, still proceed with the shutter tap rather than
            // failing the whole capture over an optional detail step.
            val zoomed = service.setZoom(TELEMACRO_ZOOM_LABEL)
            Log.i(TAG, "Telemacro zoom set: $zoomed")

            handler.postDelayed({
                val tapped = service.tapShutter()
                if (!tapped) {
                    Log.e(TAG, "Shutter tap failed")
                    returnToCaptureCam(activity)
                    onResult(null)
                    return@postDelayed
                }
                waitForNewPhoto(activity, baselineNewestId, startedAt = System.currentTimeMillis()) { uri ->
                    returnToCaptureCam(activity)
                    if (uri == null) {
                        Log.e(TAG, "No new photo appeared in MediaStore after shutter tap")
                        onResult(null)
                        return@waitForNewPhoto
                    }
                    val bytes = try {
                        activity.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                    } catch (e: Exception) {
                        Log.e(TAG, "Failed reading captured photo bytes", e)
                        null
                    }
                    onResult(bytes)
                }
            }, ZOOM_SETTLE_MS)
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
