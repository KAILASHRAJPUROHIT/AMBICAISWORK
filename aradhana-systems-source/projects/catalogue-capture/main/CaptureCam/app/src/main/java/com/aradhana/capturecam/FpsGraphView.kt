package com.aradhana.capturecam

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.util.AttributeSet
import android.view.View

/**
 * Rolling live-fps sparkline for on-device diagnosis (2026-08-26). Renders
 * the last [MAX_SAMPLES] per-frame instantaneous fps values fed via
 * [addSample] -- call only from the main thread. A flat, near-25 line means
 * healthy delivery; a jagged line or dips toward zero is a real stutter,
 * visible on the tablet itself instead of requiring a logcat pull.
 */
class FpsGraphView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val samples = ArrayDeque<Float>()
    private var latestFps: Float = 0f

    private val linePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(74, 222, 128)
        strokeWidth = 3f
        style = Paint.Style.STROKE
    }
    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(60, 74, 222, 128)
        style = Paint.Style.FILL
    }
    private val gridPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(60, 255, 255, 255)
        strokeWidth = 1f
        style = Paint.Style.STROKE
    }
    private val dangerPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(248, 113, 113)
        strokeWidth = 3f
        style = Paint.Style.STROKE
    }
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textSize = 28f
        isFakeBoldText = true
    }

    /** Appends one instantaneous-fps sample and redraws. Main thread only. */
    fun addSample(fps: Float) {
        latestFps = fps
        samples.addLast(fps.coerceIn(0f, MAX_SCALE_FPS))
        while (samples.size > MAX_SAMPLES) samples.removeFirst()
        invalidate()
    }

    fun clear() {
        samples.clear()
        latestFps = 0f
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val w = width.toFloat()
        val h = height.toFloat()
        if (w <= 0f || h <= 0f) return

        // Reference gridlines at 25 and 12.5 fps -- the two cadences this
        // rig has actually been observed at (daylight vs low-light shutter).
        for (fps in intArrayOf(25, 12)) {
            val y = h - (fps / MAX_SCALE_FPS) * h
            canvas.drawLine(0f, y, w, y, gridPaint)
        }

        if (samples.size >= 2) {
            val stepX = w / (MAX_SAMPLES - 1)
            val path = android.graphics.Path()
            val fillPath = android.graphics.Path()
            val startX = w - (samples.size - 1) * stepX
            samples.forEachIndexed { index, fps ->
                val x = startX + index * stepX
                val y = h - (fps / MAX_SCALE_FPS) * h
                if (index == 0) {
                    path.moveTo(x, y)
                    fillPath.moveTo(x, h)
                    fillPath.lineTo(x, y)
                } else {
                    path.lineTo(x, y)
                    fillPath.lineTo(x, y)
                }
            }
            fillPath.lineTo(startX + (samples.size - 1) * stepX, h)
            fillPath.close()
            canvas.drawPath(fillPath, fillPaint)
            // Stutter is what this view exists to show -- any sample under
            // half the healthy cadence draws in red so a dip is obvious at
            // a glance, not just a smaller wiggle in the same green line.
            val stroke = if (latestFps < STUTTER_THRESHOLD_FPS) dangerPaint else linePaint
            canvas.drawPath(path, stroke)
        }

        canvas.drawText("%.1f fps".format(latestFps), 12f, 32f, textPaint)
    }

    companion object {
        private const val MAX_SAMPLES = 120
        private const val MAX_SCALE_FPS = 30f
        private const val STUTTER_THRESHOLD_FPS = 12f
    }
}
