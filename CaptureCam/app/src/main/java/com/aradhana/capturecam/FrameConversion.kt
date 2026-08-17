package com.aradhana.capturecam

import android.graphics.Bitmap
import android.graphics.RectF
import androidx.camera.core.ImageProxy
import org.opencv.core.Core
import org.opencv.core.CvType
import org.opencv.core.Mat
import java.io.ByteArrayOutputStream

/** YUV ImageProxy <-> OpenCV Mat / network JPEG conversions for the
 * tracking pipeline, kept out of MainActivity so it stays orchestration-
 * only. Two frame representations exist by design: a cheap grayscale Mat
 * (local MIL tracking, intensity/gradient features -- color doesn't help
 * MIL and grayscale is the tighter per-frame loop) and a full-color JPEG
 * (sent to DINO, which needs color -- "gold jewellery" is a color-coded
 * open-vocabulary prompt, and the earlier benchmark that proved DINO
 * viable used full color images). */
object FrameConversion {

    /** Y-plane-only grayscale Mat, upright width x height (rowStride
     * cropped away). Caller owns and must release the returned Mat. */
    fun imageProxyToGrayMat(imageProxy: ImageProxy): Mat {
        val plane = imageProxy.planes[0]
        val buffer = plane.buffer
        val rowStride = plane.rowStride
        val width = imageProxy.width
        val height = imageProxy.height
        val bytes = ByteArray(buffer.remaining())
        buffer.get(bytes)
        val raw = Mat(height, rowStride, CvType.CV_8UC1)
        raw.put(0, 0, bytes)
        if (rowStride == width) return raw
        val cropped = Mat(raw, org.opencv.core.Rect(0, 0, width, height)).clone()
        raw.release()
        return cropped
    }

    /** Rotates a sensor-space Mat to upright using the SAME convention as
     * MainActivity.uprightPoint (90 -> CW, 270 -> CCW). Returns the input
     * unchanged (same object) for rotation 0 -- caller must not double-
     * release in that case. */
    fun rotateMatUpright(mat: Mat, rotationDegrees: Int): Mat = when (rotationDegrees) {
        90 -> Mat().also { Core.rotate(mat, it, Core.ROTATE_90_CLOCKWISE) }
        180 -> Mat().also { Core.rotate(mat, it, Core.ROTATE_180) }
        270 -> Mat().also { Core.rotate(mat, it, Core.ROTATE_90_COUNTERCLOCKWISE) }
        else -> mat
    }

    /** Converts a sensor-space normalized box (as returned by detector_server.py,
     * computed on the un-rotated JPEG this class sends it) into the same
     * upright-normalized space everything else in the pipeline uses. Mirrors
     * MainActivity.uprightPoint's corner-mapping exactly. */
    fun uprightBox(box: RectF, rotationDegrees: Int): RectF = when (rotationDegrees) {
        90 -> RectF(1f - box.bottom, box.left, 1f - box.top, box.right)
        180 -> RectF(1f - box.right, 1f - box.bottom, 1f - box.left, 1f - box.top)
        270 -> RectF(box.top, 1f - box.right, box.bottom, 1f - box.left)
        else -> RectF(box)
    }

    /** Full-color, downscaled JPEG of this frame in SENSOR space (not
     * rotated -- cheaper, and uprightBox() above compensates on the way
     * back). Used only for the network send to detector_server.py.
     * Uses CameraX's own ImageProxy.toBitmap() (camera-core 1.3+) rather
     * than a hand-rolled NV21 pack -- an early hand-rolled version produced
     * a corrupted (mostly-black, false-color-striped) frame server-side,
     * consistent with a stride/plane-interleave bug; CameraX's own
     * conversion is the well-tested path. */
    fun imageProxyToJpegColor(imageProxy: ImageProxy, targetLongEdge: Int, quality: Int): ByteArray {
        val bmp = imageProxy.toBitmap()
        val scale = targetLongEdge.toFloat() / maxOf(bmp.width, bmp.height)
        val out = ByteArrayOutputStream()
        if (scale >= 1f) {
            bmp.compress(Bitmap.CompressFormat.JPEG, quality, out)
        } else {
            val scaled = Bitmap.createScaledBitmap(bmp, (bmp.width * scale).toInt(), (bmp.height * scale).toInt(), true)
            scaled.compress(Bitmap.CompressFormat.JPEG, quality, out)
        }
        return out.toByteArray()
    }

    private fun imageProxyToNv21(imageProxy: ImageProxy): ByteArray {
        val width = imageProxy.width
        val height = imageProxy.height
        val nv21 = ByteArray(width * height * 3 / 2)

        val yPlane = imageProxy.planes[0]
        val yBuffer = yPlane.buffer
        val yRowStride = yPlane.rowStride
        var pos = 0
        if (yRowStride == width) {
            yBuffer.get(nv21, 0, minOf(yBuffer.remaining(), width * height))
            pos = width * height
        } else {
            val row = ByteArray(yRowStride)
            for (r in 0 until height) {
                val n = minOf(yRowStride, yBuffer.remaining())
                if (n <= 0) break
                yBuffer.get(row, 0, n)
                System.arraycopy(row, 0, nv21, pos, minOf(width, n))
                pos += width
            }
        }

        val uPlane = imageProxy.planes[1]
        val vPlane = imageProxy.planes[2]
        val uBytes = ByteArray(uPlane.buffer.remaining()).also { uPlane.buffer.get(it) }
        val vBytes = ByteArray(vPlane.buffer.remaining()).also { vPlane.buffer.get(it) }
        val uRowStride = uPlane.rowStride
        val uPixelStride = uPlane.pixelStride
        val vRowStride = vPlane.rowStride
        val vPixelStride = vPlane.pixelStride
        val chromaHeight = height / 2
        val chromaWidth = width / 2
        var outPos = width * height
        for (row in 0 until chromaHeight) {
            for (col in 0 until chromaWidth) {
                val uIndex = row * uRowStride + col * uPixelStride
                val vIndex = row * vRowStride + col * vPixelStride
                nv21[outPos++] = vBytes.getOrElse(vIndex) { 0 }
                nv21[outPos++] = uBytes.getOrElse(uIndex) { 0 }
            }
        }
        return nv21
    }
}
