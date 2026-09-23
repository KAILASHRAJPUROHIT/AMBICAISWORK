package com.aradhana.capturecam

import android.graphics.RectF
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/** Normalized (0..1, upright-preview-space) box -- the one coordinate
 * system shared end-to-end by DINO boxes, the MIL tracker, Kalman state,
 * and servo error terms. Everything that crosses a class boundary in the
 * tracking pipeline is one of these, never raw pixels. */
data class NormalizedBox(val left: Float, val top: Float, val right: Float, val bottom: Float) {
    val cx: Float get() = (left + right) / 2f
    val cy: Float get() = (top + bottom) / 2f
    val w: Float get() = right - left
    val h: Float get() = bottom - top

    fun iou(other: NormalizedBox): Float {
        val ix = (min(right, other.right) - max(left, other.left)).coerceAtLeast(0f)
        val iy = (min(bottom, other.bottom) - max(top, other.top)).coerceAtLeast(0f)
        val inter = ix * iy
        val union = w * h + other.w * other.h - inter
        return if (union <= 0f) 0f else inter / union
    }

    fun centerDist(other: NormalizedBox): Float {
        val dx = cx - other.cx
        val dy = cy - other.cy
        return sqrt(dx * dx + dy * dy)
    }

    fun toRectF() = RectF(left, top, right, bottom)

    companion object {
        fun fromXYWH(x: Float, y: Float, w: Float, h: Float) = NormalizedBox(x, y, x + w, y + h)
        fun fromCenterSize(cx: Float, cy: Float, w: Float, h: Float) =
            NormalizedBox(cx - w / 2f, cy - h / 2f, cx + w / 2f, cy + h / 2f)
    }
}
