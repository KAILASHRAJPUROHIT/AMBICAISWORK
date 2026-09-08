package com.aradhana.capturecam

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Typeface
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
    private var displayTarget: RectF? = null
    private var displayGuide: RectF? = null
    private var displayStandGuide: RectF? = null
    private var standGuideReady = false
    private var compositionProfile: CaptureCompositionProfiles.Profile? = null
    private var targetConfirmed = false
    private var sourceAspect: Float = 1f
    private var fitCenter = false
    private var cameraAssists: CameraAssistAnalyzer.Result? = null
    private var cameraFocusPoint: FloatArray? = null
    private var cameraFocusState: Int? = null

    private val paint = Paint().apply {
        color = Color.RED
        style = Paint.Style.FILL
        isAntiAlias = true
    }
    private val dotRadiusPx = 5f
    private val targetPaint = Paint().apply {
        color = Color.YELLOW
        style = Paint.Style.STROKE
        strokeWidth = 5f
        isAntiAlias = true
    }
    private val guidePaint = Paint().apply {
        color = Color.CYAN
        style = Paint.Style.STROKE
        strokeWidth = 3f
        pathEffect = DashPathEffect(floatArrayOf(14f, 10f), 0f)
        isAntiAlias = true
    }
    private val standGuidePaint = Paint().apply {
        color = Color.rgb(245, 158, 11)
        style = Paint.Style.STROKE
        strokeWidth = 7f
        pathEffect = DashPathEffect(floatArrayOf(22f, 13f), 0f)
        isAntiAlias = true
    }
    private val silhouettePaint = Paint().apply {
        color = Color.rgb(245, 158, 11)
        style = Paint.Style.STROKE
        strokeWidth = 5f
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        isAntiAlias = true
    }
    private val peakingPaint = Paint().apply {
        color = Color.rgb(170, 255, 0)
        style = Paint.Style.STROKE
        strokeWidth = 2.5f
        strokeCap = Paint.Cap.ROUND
        isAntiAlias = true
    }
    private val highlightClipPaint = Paint().apply {
        color = Color.RED
        style = Paint.Style.STROKE
        strokeWidth = 3f
        isAntiAlias = true
    }
    private val shadowClipPaint = Paint().apply {
        color = Color.rgb(0, 145, 255)
        style = Paint.Style.STROKE
        strokeWidth = 3f
        isAntiAlias = true
    }
    private val cameraFocusPaint = Paint().apply {
        style = Paint.Style.STROKE
        strokeWidth = 5f
        isAntiAlias = true
    }
    private val histogramBackgroundPaint = Paint().apply {
        color = 0xB8000000.toInt()
        style = Paint.Style.FILL
    }
    private val histogramPaint = Paint().apply {
        color = Color.WHITE
        style = Paint.Style.FILL
        alpha = 210
    }
    private val histogramTextPaint = Paint().apply {
        color = Color.WHITE
        textSize = 24f
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        isAntiAlias = true
    }

    /** Camera-derived focus target + state. State follows Sony's focal-info
     * values: 2/6 focused, 3/7 failed, 5 tracking/scanning. */
    fun updateCameraFocus(normalizedX: Float?, normalizedY: Float?, sonyState: Int?) {
        cameraFocusPoint = if (normalizedX != null && normalizedY != null) {
            floatArrayOf(normalizedX.coerceIn(0f, 1f), normalizedY.coerceIn(0f, 1f))
        } else null
        cameraFocusState = sonyState
        invalidate()
    }

    fun updateCameraAssists(result: CameraAssistAnalyzer.Result?) {
        cameraAssists = result
        invalidate()
    }

    /** Centered frame the ornament should fill when the 16-50mm lens is at
     * its verified 50mm optical limit. Fractions are in the already-upright
     * Sony Live View coordinate space. This is display-only and can never
     * enter the full-resolution camera JPEG. */
    fun updateStandGuide(widthFraction: Float, heightFraction: Float, ready: Boolean) {
        if (!widthFraction.isFinite() || !heightFraction.isFinite() ||
            widthFraction <= 0f || heightFraction <= 0f
        ) {
            clearStandGuide()
            return
        }
        val width = widthFraction.coerceIn(0.01f, 0.98f)
        val height = heightFraction.coerceIn(0.01f, 0.98f)
        displayStandGuide = RectF(
            (1f - width) / 2f,
            (1f - height) / 2f,
            (1f + width) / 2f,
            (1f + height) / 2f
        )
        standGuideReady = ready
        invalidate()
    }

    fun updateCompositionGuide(
        profile: CaptureCompositionProfiles.Profile,
        widthFraction: Float,
        heightFraction: Float,
        ready: Boolean
    ) {
        compositionProfile = profile
        updateStandGuide(widthFraction, heightFraction, ready)
    }

    fun clearStandGuide() {
        displayStandGuide = null
        standGuideReady = false
        compositionProfile = null
        invalidate()
    }

    private fun drawCompositionSilhouette(
        canvas: Canvas,
        rect: RectF,
        silhouette: CaptureCompositionProfiles.Silhouette
    ) {
        val p = silhouettePaint
        val cx = rect.centerX()
        val cy = rect.centerY()
        val w = rect.width()
        val h = rect.height()
        fun oval(l: Float, t: Float, r: Float, b: Float) =
            canvas.drawOval(RectF(l, t, r, b), p)
        fun drop(centerX: Float, top: Float, width: Float, height: Float) {
            val path = Path().apply {
                moveTo(centerX, top)
                cubicTo(centerX - width * 0.58f, top + height * 0.35f,
                    centerX - width * 0.45f, top + height * 0.76f, centerX, top + height)
                cubicTo(centerX + width * 0.45f, top + height * 0.76f,
                    centerX + width * 0.58f, top + height * 0.35f, centerX, top)
            }
            canvas.drawPath(path, p)
        }
        when (silhouette) {
            CaptureCompositionProfiles.Silhouette.RING -> {
                oval(cx - w * .30f, cy - h * .36f, cx + w * .30f, cy + h * .36f)
                oval(cx - w * .17f, cy - h * .22f, cx + w * .17f, cy + h * .22f)
                canvas.drawCircle(cx, cy - h * .40f, min(w, h) * .09f, p)
            }
            CaptureCompositionProfiles.Silhouette.CIRCLE -> {
                oval(rect.left + w * .08f, rect.top + h * .08f, rect.right - w * .08f, rect.bottom - h * .08f)
                oval(rect.left + w * .19f, rect.top + h * .19f, rect.right - w * .19f, rect.bottom - h * .19f)
            }
            CaptureCompositionProfiles.Silhouette.OPEN_CURVE -> {
                val path = Path().apply {
                    moveTo(rect.left + w * .05f, cy - h * .05f)
                    cubicTo(rect.left + w * .18f, rect.bottom - h * .02f,
                        rect.right - w * .18f, rect.bottom - h * .02f,
                        rect.right - w * .05f, cy - h * .05f)
                }
                canvas.drawPath(path, p)
            }
            CaptureCompositionProfiles.Silhouette.HOOP_PAIR -> {
                oval(rect.left + w * .08f, rect.top + h * .08f, cx - w * .05f, rect.bottom - h * .08f)
                oval(cx + w * .05f, rect.top + h * .08f, rect.right - w * .08f, rect.bottom - h * .08f)
            }
            CaptureCompositionProfiles.Silhouette.STUD_PAIR -> {
                canvas.drawCircle(cx - w * .23f, cy, min(w, h) * .16f, p)
                canvas.drawCircle(cx + w * .23f, cy, min(w, h) * .16f, p)
            }
            CaptureCompositionProfiles.Silhouette.DROP_PAIR -> {
                drop(cx - w * .23f, rect.top + h * .08f, w * .28f, h * .82f)
                drop(cx + w * .23f, rect.top + h * .08f, w * .28f, h * .82f)
            }
            CaptureCompositionProfiles.Silhouette.LONG_VERTICAL -> {
                canvas.drawLine(cx, rect.top + h * .03f, cx, rect.bottom - h * .30f, p)
                drop(cx, rect.bottom - h * .36f, w * .55f, h * .32f)
            }
            CaptureCompositionProfiles.Silhouette.NECK_CURVE -> {
                val path = Path().apply {
                    moveTo(rect.left + w * .04f, rect.top + h * .10f)
                    cubicTo(rect.left + w * .18f, rect.bottom - h * .04f,
                        rect.right - w * .18f, rect.bottom - h * .04f,
                        rect.right - w * .04f, rect.top + h * .10f)
                }
                canvas.drawPath(path, p)
                canvas.drawCircle(cx, rect.bottom - h * .07f, min(w, h) * .04f, p)
            }
            CaptureCompositionProfiles.Silhouette.PENDANT -> {
                canvas.drawCircle(cx, rect.top + h * .10f, min(w, h) * .06f, p)
                drop(cx, rect.top + h * .17f, w * .68f, h * .76f)
            }
            CaptureCompositionProfiles.Silhouette.PENDANT_SET -> {
                canvas.drawCircle(cx, rect.top + h * .08f, min(w, h) * .04f, p)
                drop(cx, rect.top + h * .14f, w * .34f, h * .52f)
                drop(rect.left + w * .18f, rect.top + h * .56f, w * .20f, h * .34f)
                drop(rect.right - w * .18f, rect.top + h * .56f, w * .20f, h * .34f)
            }
            CaptureCompositionProfiles.Silhouette.CRESCENT -> {
                canvas.drawArc(RectF(rect.left + w * .05f, rect.top + h * .08f,
                    rect.right - w * .05f, rect.bottom - h * .02f), 205f, 130f, false, p)
                canvas.drawArc(RectF(rect.left + w * .18f, rect.top + h * .22f,
                    rect.right - w * .18f, rect.bottom - h * .15f), 205f, 130f, false, p)
            }
            CaptureCompositionProfiles.Silhouette.WATI -> {
                canvas.drawCircle(cx, rect.top + h * .12f, min(w, h) * .07f, p)
                oval(rect.left + w * .10f, cy - h * .18f, cx - w * .02f, cy + h * .28f)
                oval(cx + w * .02f, cy - h * .18f, rect.right - w * .10f, cy + h * .28f)
            }
            CaptureCompositionProfiles.Silhouette.COIN -> {
                oval(rect.left + w * .08f, rect.top + h * .08f, rect.right - w * .08f, rect.bottom - h * .08f)
                oval(rect.left + w * .18f, rect.top + h * .18f, rect.right - w * .18f, rect.bottom - h * .18f)
            }
            CaptureCompositionProfiles.Silhouette.ARMLET -> {
                val path = Path().apply {
                    moveTo(rect.left + w * .04f, rect.top + h * .22f)
                    lineTo(cx, rect.bottom - h * .08f)
                    lineTo(rect.right - w * .04f, rect.top + h * .22f)
                }
                canvas.drawPath(path, p)
            }
        }
    }

    /** [points] and [rotationDegrees] straight from MaterialDetector.Result
     * and the ImageProxy that produced it. Pass an empty list to clear. */
    fun update(
        points: List<MaterialDetector.Point>,
        sourceWidth: Int,
        sourceHeight: Int,
        rotationDegrees: Int,
        fitCenter: Boolean = false
    ) {
        this.fitCenter = fitCenter
        displayTarget = null
        displayGuide = null
        targetConfirmed = false
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

    /** Sony deterministic tracking overlay: central acquisition guide,
     * one selected component, and only that component's strict-gold dots. */
    fun updateTarget(
        points: List<MaterialDetector.Point>,
        target: MaterialDetector.Bounds?,
        guide: MaterialDetector.Bounds?,
        sourceWidth: Int,
        sourceHeight: Int,
        rotationDegrees: Int,
        confirmed: Boolean
    ) {
        targetConfirmed = confirmed
        if (sourceWidth <= 0 || sourceHeight <= 0) {
            displayPoints = emptyList()
            displayTarget = null
            displayGuide = null
            invalidate()
            return
        }
        displayPoints = points.map { point -> rotatePoint(point.x, point.y, rotationDegrees) }
        displayTarget = target?.let { rotateBounds(it, rotationDegrees) }
        displayGuide = guide?.let { rotateBounds(it, rotationDegrees) }
        sourceAspect = if (rotationDegrees == 90 || rotationDegrees == 270) {
            sourceHeight.toFloat() / sourceWidth.toFloat()
        } else {
            sourceWidth.toFloat() / sourceHeight.toFloat()
        }
        invalidate()
    }

    private fun rotatePoint(x: Float, y: Float, rotationDegrees: Int): FloatArray =
        when (rotationDegrees) {
            90 -> floatArrayOf(1f - y, x)
            180 -> floatArrayOf(1f - x, 1f - y)
            270 -> floatArrayOf(y, 1f - x)
            else -> floatArrayOf(x, y)
        }

    private fun rotateBounds(bounds: MaterialDetector.Bounds, rotationDegrees: Int): RectF {
        val corners = arrayOf(
            rotatePoint(bounds.x0, bounds.y0, rotationDegrees),
            rotatePoint(bounds.x1, bounds.y0, rotationDegrees),
            rotatePoint(bounds.x0, bounds.y1, rotationDegrees),
            rotatePoint(bounds.x1, bounds.y1, rotationDegrees)
        )
        return RectF(
            corners.minOf { it[0] }, corners.minOf { it[1] },
            corners.maxOf { it[0] }, corners.maxOf { it[1] }
        )
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val vw = width.toFloat()
        val vh = height.toFloat()
        if (vw <= 0f || vh <= 0f) return

        // Phone PreviewView uses FILL_CENTER (cover + crop). Sony's ImageView
        // uses fitCenter (contain + letterbox). The same overlay sits above
        // both, so its point transform must match the active preview exactly.
        val viewAspect = vw / vh
        val renderedWidth: Float
        val renderedHeight: Float
        if (fitCenter) {
            if (sourceAspect > viewAspect) {
                renderedWidth = vw
                renderedHeight = vw / sourceAspect
            } else {
                renderedHeight = vh
                renderedWidth = vh * sourceAspect
            }
        } else {
            if (sourceAspect > viewAspect) {
                renderedHeight = vh
                renderedWidth = vh * sourceAspect
            } else {
                renderedWidth = vw
                renderedHeight = vw / sourceAspect
            }
        }
        val offsetX = (vw - renderedWidth) / 2f
        val offsetY = (vh - renderedHeight) / 2f

        fun screenRect(normalized: RectF): RectF = RectF(
            normalized.left * renderedWidth + offsetX,
            normalized.top * renderedHeight + offsetY,
            normalized.right * renderedWidth + offsetX,
            normalized.bottom * renderedHeight + offsetY
        )
        displayStandGuide?.let {
            standGuidePaint.color = if (standGuideReady) Color.rgb(34, 197, 94)
            else Color.rgb(245, 158, 11)
            silhouettePaint.color = standGuidePaint.color
            val rect = screenRect(it)
            canvas.drawRect(rect, standGuidePaint)
            compositionProfile?.let { profile ->
                drawCompositionSilhouette(canvas, rect, profile.silhouette)
            }
        }
        displayGuide?.let { canvas.drawRect(screenRect(it), guidePaint) }
        displayTarget?.let {
            targetPaint.color = if (targetConfirmed) Color.GREEN else Color.YELLOW
            canvas.drawRect(screenRect(it), targetPaint)
        }

        cameraFocusPoint?.let { point ->
            val halfW = 0.055f
            val halfH = 0.075f
            cameraFocusPaint.color = when (cameraFocusState) {
                2, 6 -> Color.GREEN
                3, 7 -> Color.RED
                else -> Color.YELLOW
            }
            canvas.drawRect(
                screenRect(
                    RectF(
                        (point[0] - halfW).coerceAtLeast(0f),
                        (point[1] - halfH).coerceAtLeast(0f),
                        (point[0] + halfW).coerceAtMost(1f),
                        (point[1] + halfH).coerceAtMost(1f)
                    )
                ),
                cameraFocusPaint
            )
        }

        cameraAssists?.let { assists ->
            for (mark in assists.marks) {
                val sx = mark.x * renderedWidth + offsetX
                val sy = mark.y * renderedHeight + offsetY
                when (mark.kind) {
                    CameraAssistAnalyzer.MarkKind.PEAKING ->
                        canvas.drawLine(sx - 3f, sy, sx + 3f, sy, peakingPaint)
                    CameraAssistAnalyzer.MarkKind.HIGHLIGHT_CLIP ->
                        canvas.drawLine(sx - 5f, sy + 5f, sx + 5f, sy - 5f, highlightClipPaint)
                    CameraAssistAnalyzer.MarkKind.SHADOW_CLIP ->
                        canvas.drawLine(sx - 5f, sy - 5f, sx + 5f, sy + 5f, shadowClipPaint)
                }
            }

            val panelWidth = min(430f, vw * 0.48f)
            val panelHeight = 118f
            val panelLeft = vw - panelWidth - 18f
            val panelTop = 18f
            canvas.drawRoundRect(
                RectF(panelLeft, panelTop, vw - 18f, panelTop + panelHeight),
                12f,
                12f,
                histogramBackgroundPaint
            )
            val chartLeft = panelLeft + 12f
            val chartRight = vw - 30f
            val chartTop = panelTop + 10f
            val chartBottom = panelTop + 72f
            val binWidth = (chartRight - chartLeft) / assists.histogram.size.coerceAtLeast(1)
            assists.histogram.forEachIndexed { index, value ->
                canvas.drawRect(
                    chartLeft + index * binWidth,
                    chartBottom - value.coerceIn(0f, 1f) * (chartBottom - chartTop),
                    chartLeft + (index + 1) * binWidth - 1f,
                    chartBottom,
                    histogramPaint
                )
            }
            val exposureLabel = if (assists.exposureOk) "EXPOSURE OK" else "ADJUST EXPOSURE"
            val text = "UNDER %.1f%%  |  %s  |  CLIPPED %.1f%%".format(
                assists.shadowClipFraction * 100f,
                exposureLabel,
                assists.highlightClipFraction * 100f
            )
            canvas.drawText(text, panelLeft + 12f, panelTop + 104f, histogramTextPaint)
        }

        for (p in displayPoints) {
            val screenX = p[0] * renderedWidth + offsetX
            val screenY = p[1] * renderedHeight + offsetY
            if (screenX < -dotRadiusPx || screenX > vw + dotRadiusPx ||
                screenY < -dotRadiusPx || screenY > vh + dotRadiusPx
            ) continue
            canvas.drawCircle(screenX, screenY, dotRadiusPx, paint)
        }
    }
}
