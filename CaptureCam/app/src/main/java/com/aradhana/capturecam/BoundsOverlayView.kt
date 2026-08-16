package com.aradhana.capturecam

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.util.AttributeSet
import android.view.View
import kotlin.math.max
import kotlin.math.min

/**
 * Draws a live scatter of red dots over every detected gold/silver/sparkle
 * sample point on top of the camera preview -- DSLR-style focus peaking,
 * purely a screen overlay. It never touches the actual captured photo:
 * ImageCapture pulls the JPEG straight from the camera pipeline,
 * independent of anything drawn here.
 *
 * MaterialDetector's points are normalized (0..1) against the
 * ImageAnalysis frame in its own SENSOR orientation, not the rotated/
 * cropped orientation PreviewView actually displays it in (FILL_CENTER:
 * scaled to cover the view, centre-cropping the longer axis) -- update()
 * takes the frame's rotationDegrees and does both transforms per point
 * before drawing.
 */
class BoundsOverlayView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private var displayPoints: List<FloatArray> = emptyList() // each [x,y] normalized in DISPLAY space
    private var sourceAspect: Float = 1f

    private val paint = Paint().apply {
        color = Color.RED
        style = Paint.Style.FILL
        isAntiAlias = true
    }
    private val dotRadiusPx = 5f

    /** [points] and [rotationDegrees] straight from MaterialDetector.Result
     * and the ImageProxy that produced it. Pass an empty list to clear. */
    fun update(points: List<MaterialDetector.Point>, sourceWidth: Int, sourceHeight: Int, rotationDegrees: Int) {
        if (points.isEmpty() || sourceWidth <= 0 || sourceHeight <= 0) {
            displayPoints = emptyList()
            invalidate()
            return
        }
        // Rotate each normalized point from the analyzer's raw sensor-space
        // coordinates into the same orientation PreviewView displays. For a
        // clockwise image rotation by rotationDegrees, a point (x,y) in the
        // unrotated image maps to the rotated image at:
        //   90:  (1-y, x)      180: (1-x, 1-y)      270: (y, 1-x)
        // (standard EXIF/CW-rotation point transform; the box-based version
        // of this file had the terms swapped, which is why the highlighted
        // region used to land in the wrong part of the frame.)
        displayPoints = points.map { p ->
            when (rotationDegrees) {
                90 -> floatArrayOf(1f - p.y, p.x)
                180 -> floatArrayOf(1f - p.x, 1f - p.y)
                270 -> floatArrayOf(p.y, 1f - p.x)
                else -> floatArrayOf(p.x, p.y)
            }
        }
        sourceAspect = if (rotationDegrees == 90 || rotationDegrees == 270) {
            sourceHeight.toFloat() / sourceWidth.toFloat()
        } else {
            sourceWidth.toFloat() / sourceHeight.toFloat()
        }
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (displayPoints.isEmpty()) return
        val vw = width.toFloat()
        val vh = height.toFloat()
        if (vw <= 0f || vh <= 0f) return

        // FILL_CENTER mapping: the rotated source is scaled to COVER the
        // view (PreviewView's default scale type), so whichever axis is
        // relatively larger gets centre-cropped.
        val viewAspect = vw / vh
        val renderedWidth: Float
        val renderedHeight: Float
        if (sourceAspect > viewAspect) {
            renderedHeight = vh
            renderedWidth = vh * sourceAspect
        } else {
            renderedWidth = vw
            renderedHeight = vw / sourceAspect
        }
        val cropX = (renderedWidth - vw) / 2f
        val cropY = (renderedHeight - vh) / 2f

        for (p in displayPoints) {
            val screenX = p[0] * renderedWidth - cropX
            val screenY = p[1] * renderedHeight - cropY
            if (screenX < -dotRadiusPx || screenX > vw + dotRadiusPx ||
                screenY < -dotRadiusPx || screenY > vh + dotRadiusPx
            ) continue
            canvas.drawCircle(screenX, screenY, dotRadiusPx, paint)
        }
    }
}
