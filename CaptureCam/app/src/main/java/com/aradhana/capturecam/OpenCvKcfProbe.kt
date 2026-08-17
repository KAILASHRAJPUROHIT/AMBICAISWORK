package com.aradhana.capturecam

import android.graphics.Bitmap
import android.util.Log
import org.opencv.android.OpenCVLoader
import org.opencv.android.Utils
import org.opencv.core.Mat
import org.opencv.core.Rect
import org.opencv.tracking.TrackerKCF

/**
 * One-shot probe: confirms org.opencv.tracking.TrackerKCF actually links
 * and runs on-device, not just compiles -- per the explicit instruction
 * "Maven AAR -> compile TrackerKCF -> run one frame test -> only then
 * decide whether there is a real blocker." Called once from onCreate,
 * logs PASS/FAIL, has zero effect on the rest of the app either way.
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

            val tracker = TrackerKCF.create()
            val bbox = Rect(50, 50, 60, 60)
            tracker.init(mat, bbox)

            val updated = Rect()
            val ok = tracker.update(mat, updated)
            Log.i(TAG, "PASS: TrackerKCF.create()/init()/update() all ran. update()=$ok box=$updated")
        } catch (e: Throwable) {
            Log.e(TAG, "FAIL: TrackerKCF probe threw", e)
        }
    }
}
