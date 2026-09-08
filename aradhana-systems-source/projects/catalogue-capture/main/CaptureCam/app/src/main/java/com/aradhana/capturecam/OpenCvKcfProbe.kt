package com.aradhana.capturecam

import android.graphics.Bitmap
import android.util.Log
import org.opencv.android.OpenCVLoader
import org.opencv.android.Utils
import org.opencv.core.Mat
import org.opencv.core.Rect
import org.opencv.video.TrackerMIL

/**
 * One-shot probe: confirms a real OpenCV tracker actually links and runs
 * on-device, not just compiles. TrackerKCF/CSRT (opencv_contrib) were
 * confirmed ABSENT from the official org.opencv:opencv Maven AAR --
 * "Unresolved reference: tracking" at compile time, and direct inspection
 * of the AAR's classes.jar shows no org.opencv.tracking package at all.
 * TrackerMIL, however, IS present in org.opencv.video (part of the core
 * video module, no contrib needed) -- same role (classical single-object
 * tracker, no extra model file to download), different underlying
 * algorithm (Multiple Instance Learning vs correlation filter). Using this
 * instead. Called once from onCreate, logs PASS/FAIL, has zero effect on
 * the rest of the app either way.
 */
object OpenCvKcfProbe {
    private const val TAG = "OpenCvKcfProbe"

    fun run() {
        try {
            val loaded = OpenCVLoader.initLocal()
            Log.i(TAG, "OpenCVLoader.initLocal() = $loaded, version=${org.opencv.core.Core.VERSION}")

            val bmp = Bitmap.createBitmap(200, 200, Bitmap.Config.ARGB_8888)
            bmp.eraseColor(android.graphics.Color.GRAY)
            val mat = Mat()
            Utils.bitmapToMat(bmp, mat)

            val tracker = TrackerMIL.create()
            val bbox = Rect(50, 50, 60, 60)
            tracker.init(mat, bbox)

            val updated = Rect()
            val ok = tracker.update(mat, updated)
            Log.i(TAG, "PASS: TrackerMIL.create()/init()/update() all ran. update()=$ok box=$updated")
        } catch (e: Throwable) {
            Log.e(TAG, "FAIL: TrackerMIL probe threw", e)
        }
    }
}
