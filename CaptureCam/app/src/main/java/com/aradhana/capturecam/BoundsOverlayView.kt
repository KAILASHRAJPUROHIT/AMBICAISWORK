package com.aradhana.capturecam

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View

/**
 * Draws a live red outline around the detected gold/silver blob on top of
 * the camera preview -- DSLR-style focus peaking, purely a screen overlay.
 * It never touches the actual captured photo: ImageCapture pulls the JPEG
 * straight from the camera pipeline, independent of anything drawn here.
 *
 * MaterialDetector's bounds are normalized (0..1) against the ImageAnalysis
 * frame in its own SENSOR orientation, not the rotated/cropped orientation
 * PreviewView actually displays it in (FILL_CENTER: scaled to cover the
 * view, centre-cropping the longer axis) -- update() takes the frame's
 * rotationDegrees and does both transforms before drawing.
 */
class BoundsOverlayView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private var displayRect: RectF? = null
    private var sourceAspect: Float = 1f

    private val paint = Paint().apply {
        color = Color.RED
        style = Paint.Style.STROKE
        strokeWidth = 6f
        isAntiAlias = true
    }

    /** [bounds] and [rotationDegrees] straight from MaterialDetector.Result
     * and the ImageProxy that produced it. Pass bounds=null to clear. */
    fun update(bounds: MaterialDetector.Bounds?, sourceWidth: Int, sourceHeight: Int, rotationDegrees: Int) {
        if (bounds == null || sourceWidth <= 0 || sourceHeight <= 0) {
            displayRect = null
            invalidate()
            return
        }
        // Rotate the normalized box from the analyzer's raw sensor-space
        // coordinates into the same orientation PreviewView displays.
        displayRect = when (rotationDegrees) {
            90 -> RectF(bounds.y0, 1f - bounds.x1, bounds.y1, 1f - bounds.x0)
            180 -> RectF(1f - bounds.x1, 1f - bounds.y1, 1f - bounds.x0, 1f - bounds.y0)
            270 -> RectF(1f - bounds.y1, bounds.x0, 1f - bounds.y0, bounds.x1)
            else -> RectF(bounds.x0, bounds.y0, bounds.x1, bounds.y1)
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
        val r = displayRect ?: return
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

        canvas.drawRoundRect(
            r.left * renderedWidth - cropX,
            r.top * renderedHeight - cropY,
            r.right * renderedWidth - cropX,
            r.bottom * renderedHeight - cropY,
            12f, 12f, paint
        )
    }
}
