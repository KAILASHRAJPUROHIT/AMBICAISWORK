package com.aradhana.capturecam

import android.graphics.RectF
import android.util.Log
import org.opencv.core.CvType
import org.opencv.core.Mat
import org.opencv.core.Rect
import org.opencv.video.KalmanFilter
import org.opencv.video.TrackerMIL

/**
 * Local, per-frame jewellery tracker: seeded from a Grounding DINO box
 * (the "eyes", ~3fps over the network), then owns frame-to-frame following
 * on-device via OpenCV's TrackerMIL (the correlation-filter-class tracker
 * actually present in the official Maven AAR -- KCF/CSRT confirmed absent,
 * see OpenCvKcfProbe's doc comment) at preview speed, with a KalmanFilter
 * smoothing the raw per-frame box center into a stable position+velocity
 * estimate. DINO periodically corrects/reseeds this; MIL bridges every
 * frame in between, including through gimbal motion.
 *
 * Bridges brief misses rather than declaring the target lost on one bad
 * frame: 1-5 consecutive MIL failures still returns a Kalman-PREDICTED
 * position (predicted=true); beyond that, returns null (genuinely lost,
 * caller should fall back to search).
 */
class JewelleryTracker {

    data class TrackResult(
        val cx: Float, val cy: Float, val w: Float, val h: Float,
        val predicted: Boolean,
    )

    private var tracker: TrackerMIL? = null
    private var kalman: KalmanFilter? = null
    private var consecutiveMisses = 0
    private var frameW = 1
    private var frameH = 1

    val isTracking: Boolean get() = tracker != null

    /** (Re)seeds the tracker at [box] (normalized 0..1, upright frame
     * space) on the given frame. Called both for a fresh DINO acquisition
     * and for a periodic DINO reseed of an already-tracking target. */
    fun seed(mat: Mat, box: RectF) {
        // Explicit reseed: drop any existing tracker FIRST, never hold two
        // native TrackerMIL instances alive at once (one nulled-out, one
        // freshly created) -- the old one's native object is a real
        // resource, not just a Kotlin reference to clear later.
        tracker = null
        frameW = mat.cols()
        frameH = mat.rows()
        val px = (box.left * frameW).toInt().coerceIn(0, frameW - 1)
        val py = (box.top * frameH).toInt().coerceIn(0, frameH - 1)
        val pw = (box.width() * frameW).toInt().coerceIn(4, frameW - px)
        val ph = (box.height() * frameH).toInt().coerceIn(4, frameH - py)

        val t = TrackerMIL.create()
        t.init(mat, Rect(px, py, pw, ph))
        tracker = t
        consecutiveMisses = 0

        val kf = KalmanFilter(4, 2, 0, CvType.CV_32F)
        // Constant-velocity model: state=[cx,cy,vx,vy], measurement=[cx,cy].
        kf.set_transitionMatrix(Mat.eye(4, 4, CvType.CV_32F).also {
            it.put(0, 2, 1.0)
            it.put(1, 3, 1.0)
        })
        kf.set_measurementMatrix(Mat.zeros(2, 4, CvType.CV_32F).also {
            it.put(0, 0, 1.0)
            it.put(1, 1, 1.0)
        })
        val processNoise = Mat.eye(4, 4, CvType.CV_32F)
        for (i in 0 until 4) processNoise.put(i, i, 1e-2)
        kf.set_processNoiseCov(processNoise)
        val measurementNoise = Mat.eye(2, 2, CvType.CV_32F)
        for (i in 0 until 2) measurementNoise.put(i, i, 1e-1)
        kf.set_measurementNoiseCov(measurementNoise)
        val cx = box.centerX() * frameW
        val cy = box.centerY() * frameH
        kf.set_statePost(Mat(4, 1, CvType.CV_32F).also {
            it.put(0, 0, cx.toDouble())
            it.put(1, 0, cy.toDouble())
            it.put(2, 0, 0.0)
            it.put(3, 0, 0.0)
        })
        kalman = kf
        lastW = box.width(); lastH = box.height()
        Log.i(TAG, "Seeded tracker at box=$box (px=$px py=$py pw=$pw ph=$ph)")
    }

    private var lastW = 0.1f
    private var lastH = 0.1f

    /** Runs on EVERY analysis frame once tracking. Returns a smoothed,
     * normalized position, or null if genuinely lost (>MAX_MISSES
     * consecutive MIL failures) -- caller should fall back to search in
     * that case. */
    fun update(mat: Mat): TrackResult? {
        val t = tracker ?: return null
        val kf = kalman ?: return null
        frameW = mat.cols(); frameH = mat.rows()

        val predicted = kf.predict()
        val predCx = predicted.get(0, 0)[0]
        val predCy = predicted.get(1, 0)[0]

        val box = Rect()
        val ok = try { t.update(mat, box) } catch (e: Exception) {
            Log.w(TAG, "TrackerMIL.update threw: ${e.message}")
            false
        }

        if (ok) {
            consecutiveMisses = 0
            val measCx = box.x + box.width / 2.0
            val measCy = box.y + box.height / 2.0
            val measurement = Mat(2, 1, CvType.CV_32F).also {
                it.put(0, 0, measCx)
                it.put(1, 0, measCy)
            }
            val corrected = kf.correct(measurement)
            val cx = (corrected.get(0, 0)[0] / frameW).toFloat()
            val cy = (corrected.get(1, 0)[0] / frameH).toFloat()
            // Size is tracked SEPARATELY from the Kalman position filter
            // (its own light exponential smoothing, not stuffed into the
            // same [cx,cy,vx,vy] state) -- zoom control cares about a
            // stable size trend, position control cares about a stable
            // position+velocity trend; conflating them means a size
            // fluctuation would perturb the position estimate and vice versa.
            val rawW = box.width.toFloat() / frameW
            val rawH = box.height.toFloat() / frameH
            lastW += SIZE_SMOOTHING * (rawW - lastW)
            lastH += SIZE_SMOOTHING * (rawH - lastH)
            return TrackResult(cx, cy, lastW, lastH, predicted = false)
        }

        consecutiveMisses += 1
        if (consecutiveMisses > MAX_MISSES) {
            Log.w(TAG, "Tracker lost after $consecutiveMisses consecutive misses")
            tracker = null
            kalman = null
            return null
        }
        // Bridge the miss with the Kalman PREDICTION alone (no correction
        // this frame) -- exactly the "1-5 missing frames -> predict"
        // behaviour from spec point 5.
        val cx = (predCx / frameW).toFloat()
        val cy = (predCy / frameH).toFloat()
        return TrackResult(cx, cy, lastW, lastH, predicted = true)
    }

    fun reset() {
        tracker = null
        kalman = null
        consecutiveMisses = 0
    }

    companion object {
        private const val TAG = "JewelleryTracker"
        private const val MAX_MISSES = 5
    }
}
