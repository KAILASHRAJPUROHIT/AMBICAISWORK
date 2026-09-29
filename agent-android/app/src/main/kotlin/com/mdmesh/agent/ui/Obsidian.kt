package com.mdmesh.agent.ui

import android.animation.ValueAnimator
import android.annotation.SuppressLint
import android.content.Context
import android.content.res.Configuration
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorFilter
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.provider.Settings
import android.util.TypedValue
import android.view.MotionEvent
import android.view.View
import android.view.animation.DecelerateInterpolator
import android.view.animation.LinearInterpolator
import android.widget.TextView
import kotlin.math.max
import kotlin.math.min

/**
 * Obsidian Pro — the agent's on-device design system, matching the web console (2026-09-28).
 *
 * Everything the tablet shows (kiosk home, Quick Controls, admin menu, agent health screen) is
 * built from these tokens, drawables and views so the product reads as one thing on every
 * screen size. All sizing goes through [Metrics], never hard-coded per device: one APK lays out
 * correctly on a 6" phone, an 8" tablet and a 12" tablet, portrait or landscape.
 */
object ObsidianPrefs {
    private const val FILE = "obsidian_ui"
    private const val KEY_APPEARANCE = "appearance"

    /** "dark" (default — the kiosk has always been dark), "light", or "system". */
    fun appearance(ctx: Context): String =
        ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE).getString(KEY_APPEARANCE, "dark") ?: "dark"

    fun setAppearance(ctx: Context, mode: String) {
        ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit().putString(KEY_APPEARANCE, mode).apply()
    }

    fun isDark(ctx: Context): Boolean = when (appearance(ctx)) {
        "light" -> false
        "system" -> (ctx.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) ==
            Configuration.UI_MODE_NIGHT_YES
        else -> true
    }
}

/** Colour tokens — identical values to the console's Obsidian Pro CSS. */
data class Palette(
    val dark: Boolean,
    val bg: Int,
    val surface: Int,
    val surface2: Int,
    val line: Int,
    val text: Int,
    val muted: Int,
    val faint: Int,
    val c1: Int,
    val c2: Int,
    val c3: Int,
    val ok: Int,
    val warn: Int,
    val alert: Int,
    val glass: Int,
    val grid: Int,
) {
    companion object {
        fun of(ctx: Context, accent: Int? = null): Palette =
            if (ObsidianPrefs.isDark(ctx)) dark(accent) else light(accent)

        fun dark(accent: Int? = null) = Palette(
            dark = true,
            bg = c("#05070D"), surface = c("#0B111C"), surface2 = c("#101826"), line = c("#1B2638"),
            text = c("#EAF2FF"), muted = c("#8594AD"), faint = c("#56657D"),
            c1 = c("#22E1FF"), c2 = accent ?: c("#A56BFF"), c3 = c("#FF4FA3"),
            ok = c("#34E7A0"), warn = c("#FFB547"), alert = c("#FF5E78"),
            glass = Color.argb(214, 11, 17, 28), grid = Color.argb(16, 120, 170, 255),
        )

        fun light(accent: Int? = null) = Palette(
            dark = false,
            bg = c("#EEF1F7"), surface = c("#FFFFFF"), surface2 = c("#F3F5FA"), line = c("#DCE2EC"),
            text = c("#0B1220"), muted = c("#5E6B80"), faint = c("#94A3B8"),
            c1 = c("#0891B2"), c2 = accent ?: c("#7C3AED"), c3 = c("#DB2777"),
            ok = c("#059669"), warn = c("#D97706"), alert = c("#DC2626"),
            glass = Color.argb(214, 255, 255, 255), grid = Color.argb(12, 15, 23, 42),
        )

        private fun c(hex: String) = Color.parseColor(hex)
    }
}

/**
 * Screen-aware sizing. Phones (smallest width < 600dp), tablets (600–839dp) and large tablets
 * (840dp+) each get their own icon size, text scale, gutters and tile width; the kiosk grid's
 * column count is derived from the real available width, so rotation and split screen just work.
 */
class Metrics(private val ctx: Context) {
    private val dm = ctx.resources.displayMetrics
    private val cfg = ctx.resources.configuration
    val swDp: Int = cfg.smallestScreenWidthDp
    val widthDp: Int = cfg.screenWidthDp
    val isPhone = swDp < 600
    val isLargeTablet = swDp >= 840

    /** Multiplier for every text size so a phone isn't crowded and a 12" tablet isn't sparse. */
    val textScale: Float = when {
        isPhone -> 0.9f
        isLargeTablet -> 1.12f
        else -> 1f
    }
    val gutterDp: Int = when {
        isPhone -> 14
        isLargeTablet -> 32
        else -> 22
    }
    val iconDp: Int = when {
        isPhone -> 50
        isLargeTablet -> 68
        else -> 58
    }
    /** Minimum width of one app tile; columns = available width / this. */
    val tileMinDp: Int = when {
        isPhone -> 80
        isLargeTablet -> 118
        else -> 100
    }
    /** Content never stretches wider than this, so landscape tablets keep a readable column. */
    val maxContentDp: Int = if (isPhone) widthDp else 1040

    fun columns(): Int {
        val usable = min(widthDp, maxContentDp) - 2 * gutterDp
        return (usable / tileMinDp).coerceIn(3, 9)
    }

    fun dp(v: Int): Int = (v * dm.density).toInt()
    fun dp(v: Float): Float = v * dm.density
    fun sp(v: Float): Float = v * textScale

    /** Sheets/dialogs: full width on phones, a centred card on tablets. */
    fun sheetWidthPx(): Int = if (isPhone) dm.widthPixels else min(dm.widthPixels, dp(600))
}

/** True when the user (or MIUI battery saver) turned animations off system-wide. */
fun animationsOff(ctx: Context): Boolean =
    runCatching { Settings.Global.getFloat(ctx.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f }
        .getOrDefault(false)

// --- Drawables -------------------------------------------------------------------------------

fun rounded(fill: Int, radiusPx: Float, stroke: Int? = null, strokePx: Int = 0): GradientDrawable =
    GradientDrawable().apply {
        shape = GradientDrawable.RECTANGLE
        cornerRadius = radiusPx
        setColor(fill)
        if (stroke != null && strokePx > 0) setStroke(strokePx, stroke)
    }

fun gradient(
    colors: IntArray,
    radiusPx: Float,
    orientation: GradientDrawable.Orientation = GradientDrawable.Orientation.TL_BR,
): GradientDrawable = GradientDrawable(orientation, colors).apply { cornerRadius = radiusPx }

fun withAlpha(color: Int, alpha: Float): Int =
    Color.argb((alpha * 255).toInt().coerceIn(0, 255), Color.red(color), Color.green(color), Color.blue(color))

/** App ground: base colour, a faint 28dp grid and two soft accent glows (cyan top-right, violet
 *  bottom-left) — the console's background, drawn natively. */
class GroundDrawable(private val p: Palette, private val gridPx: Float) : Drawable() {
    private val gridPaint = Paint().apply { color = p.grid; strokeWidth = 1f }
    private val glow = Paint(Paint.ANTI_ALIAS_FLAG)

    override fun draw(canvas: Canvas) {
        val b = bounds
        canvas.drawColor(p.bg)
        var x = 0f
        while (x < b.width()) { canvas.drawLine(x, 0f, x, b.height().toFloat(), gridPaint); x += gridPx }
        var y = 0f
        while (y < b.height()) { canvas.drawLine(0f, y, b.width().toFloat(), y, gridPaint); y += gridPx }
        val r1 = max(b.width(), b.height()) * 0.55f
        glow.shader = RadialGradient(b.width() * 0.9f, -b.height() * 0.05f, r1,
            withAlpha(p.c1, if (p.dark) 0.20f else 0.14f), Color.TRANSPARENT, Shader.TileMode.CLAMP)
        canvas.drawRect(0f, 0f, b.width().toFloat(), b.height().toFloat(), glow)
        glow.shader = RadialGradient(0f, b.height() * 1.05f, r1,
            withAlpha(p.c2, if (p.dark) 0.18f else 0.12f), Color.TRANSPARENT, Shader.TileMode.CLAMP)
        canvas.drawRect(0f, 0f, b.width().toFloat(), b.height().toFloat(), glow)
    }

    override fun setAlpha(alpha: Int) = Unit
    override fun setColorFilter(colorFilter: ColorFilter?) = Unit
    @Deprecated("Deprecated in Java")
    override fun getOpacity(): Int = PixelFormat.OPAQUE
}

// --- Text ----------------------------------------------------------------------------------------

fun TextView.style(sizeSp: Float, color: Int, weight: Int = 400, mono: Boolean = false, letterSp: Float = 0f): TextView {
    setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp)
    setTextColor(color)
    val family = if (mono) Typeface.MONOSPACE else Typeface.SANS_SERIF
    typeface = if (android.os.Build.VERSION.SDK_INT >= 28) Typeface.create(family, weight, false)
    else Typeface.create(family, if (weight >= 600) Typeface.BOLD else Typeface.NORMAL)
    letterSpacing = letterSp
    includeFontPadding = false
    return this
}

/** Paints the text with a left-to-right accent gradient (the console's gradient numerals). */
fun TextView.gradientText(from: Int, to: Int) {
    addOnLayoutChangeListener { v, l, _, r, _, _, _, _, _ ->
        (v as TextView).paint.shader = LinearGradient(0f, 0f, (r - l).toFloat(), 0f, from, to, Shader.TileMode.CLAMP)
        v.invalidate()
    }
}

// --- Motion ----------------------------------------------------------------------------------------

/** Fade + rise in, staggered by [delayMs]. Content is laid out at rest first, so nothing is ever
 *  stuck invisible if animations are disabled. */
fun View.enter(delayMs: Long = 0) {
    if (animationsOff(context)) return
    alpha = 0f
    translationY = resources.displayMetrics.density * 10
    animate().alpha(1f).translationY(0f).setStartDelay(delayMs).setDuration(380)
        .setInterpolator(DecelerateInterpolator()).start()
}

/** Gentle infinite breathing (alpha), for live indicators. Returns the animator so callers can
 *  cancel it; stops itself when the view detaches. */
fun View.breathe(periodMs: Long = 2000, minAlpha: Float = 0.35f): ValueAnimator? {
    if (animationsOff(context)) return null
    val a = ValueAnimator.ofFloat(1f, minAlpha).apply {
        duration = periodMs / 2
        repeatMode = ValueAnimator.REVERSE
        repeatCount = ValueAnimator.INFINITE
        addUpdateListener { alpha = it.animatedValue as Float }
    }
    addOnAttachStateChangeListener(object : View.OnAttachStateChangeListener {
        override fun onViewAttachedToWindow(v: View) = Unit
        override fun onViewDetachedFromWindow(v: View) { a.cancel() }
    })
    a.start()
    return a
}

/** Press feedback: shrink slightly while touched. */
@SuppressLint("ClickableViewAccessibility")
fun View.pressable() {
    setOnTouchListener { v, e ->
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> v.animate().scaleX(0.94f).scaleY(0.94f).setDuration(90).start()
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> v.animate().scaleX(1f).scaleY(1f).setDuration(140).start()
        }
        false
    }
}

// --- Custom views ------------------------------------------------------------------------------------

/** Small battery ring (percent arc; amber below 45%, red below 20%). */
class BatteryRingView(ctx: Context, private val p: Palette) : View(ctx) {
    var percent: Int = -1
        set(v) { field = v; invalidate() }
    var charging: Boolean = false
        set(v) { field = v; invalidate() }
    private val track = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = p.line }
    private val arc = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND }
    private val rect = RectF()

    override fun onDraw(canvas: Canvas) {
        val sw = width * 0.16f
        track.strokeWidth = sw
        arc.strokeWidth = sw
        rect.set(sw, sw, width - sw, height - sw)
        canvas.drawArc(rect, 0f, 360f, false, track)
        if (percent < 0) return
        arc.color = when {
            charging -> p.c1
            percent <= 20 -> p.alert
            percent <= 45 -> p.warn
            else -> p.ok
        }
        canvas.drawArc(rect, -90f, 360f * percent / 100f, false, arc)
    }
}

/** Four rising signal bars; unlit bars are faint. */
class WifiBarsView(ctx: Context, private val p: Palette) : View(ctx) {
    var bars: Int = 0
        set(v) { field = v; invalidate() }
    var connected: Boolean = true
        set(v) { field = v; invalidate() }
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val r = RectF()

    override fun onDraw(canvas: Canvas) {
        val n = 4
        val gap = width * 0.1f
        val bw = (width - gap * (n - 1)) / n
        for (i in 0 until n) {
            val h = height * (i + 1) / n.toFloat()
            val left = i * (bw + gap)
            r.set(left, height - h, left + bw, height.toFloat())
            paint.color = if (connected && i < bars) p.c1 else withAlpha(p.muted, 0.3f)
            canvas.drawRoundRect(r, bw / 3, bw / 3, paint)
        }
    }
}

/** Animated accent line (the console's shimmering underline) for the bottom of hero cards. */
class ShimmerLineView(ctx: Context, private val p: Palette) : View(ctx) {
    private val paint = Paint()
    private var phase = 0f
    private val anim: ValueAnimator? = if (animationsOff(ctx)) null else ValueAnimator.ofFloat(0f, 1f).apply {
        duration = 4000
        repeatCount = ValueAnimator.INFINITE
        interpolator = LinearInterpolator()
        addUpdateListener { phase = it.animatedValue as Float; invalidate() }
    }

    override fun onAttachedToWindow() { super.onAttachedToWindow(); anim?.start() }
    override fun onDetachedFromWindow() { anim?.cancel(); super.onDetachedFromWindow() }

    override fun onDraw(canvas: Canvas) {
        val w = width.toFloat()
        val start = -w + phase * 2 * w
        paint.shader = LinearGradient(start, 0f, start + w, 0f,
            intArrayOf(Color.TRANSPARENT, p.c1, p.c2, Color.TRANSPARENT), null, Shader.TileMode.CLAMP)
        canvas.drawRect(0f, 0f, w, height.toFloat(), paint)
    }
}

/** Ring that empties over [totalMs] from [startedAt] — the Wi-Fi auto-restore countdown. */
class CountdownRingView(ctx: Context, private val p: Palette) : View(ctx) {
    var startedAt: Long = 0
    var totalMs: Long = 1
    private val track = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = p.line }
    private val arc = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; color = p.c3 }
    private val rect = RectF()
    private val tick = object : Runnable {
        override fun run() { invalidate(); postDelayed(this, 500) }
    }

    override fun onAttachedToWindow() { super.onAttachedToWindow(); post(tick) }
    override fun onDetachedFromWindow() { removeCallbacks(tick); super.onDetachedFromWindow() }

    override fun onDraw(canvas: Canvas) {
        val sw = width * 0.13f
        track.strokeWidth = sw
        arc.strokeWidth = sw
        rect.set(sw, sw, width - sw, height - sw)
        canvas.drawArc(rect, 0f, 360f, false, track)
        val left = (1f - (System.currentTimeMillis() - startedAt).toFloat() / totalMs).coerceIn(0f, 1f)
        canvas.drawArc(rect, -90f, 360f * left, false, arc)
    }
}

/** Score ring for the health screen: gradient arc showing [value]/[total], big number inside. */
class ScoreRingView(ctx: Context, private val p: Palette) : View(ctx) {
    var value = 0
    var total = 1
    private var shown = 0f
    private val track = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = p.line }
    private val arc = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND }
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = p.text
        textAlign = Paint.Align.CENTER
        typeface = Typeface.create(Typeface.MONOSPACE, Typeface.BOLD)
    }
    private val rect = RectF()

    fun set(value: Int, total: Int) {
        this.value = value
        this.total = max(total, 1)
        val target = value.toFloat() / this.total
        if (animationsOff(context)) { shown = target; invalidate(); return }
        ValueAnimator.ofFloat(shown, target).apply {
            duration = 1100
            interpolator = DecelerateInterpolator()
            addUpdateListener { shown = it.animatedValue as Float; invalidate() }
        }.start()
    }

    override fun onDraw(canvas: Canvas) {
        val sw = width * 0.09f
        track.strokeWidth = sw
        arc.strokeWidth = sw
        rect.set(sw, sw, width - sw, height - sw)
        arc.shader = LinearGradient(0f, 0f, width.toFloat(), height.toFloat(), p.c1, p.c2, Shader.TileMode.CLAMP)
        canvas.drawArc(rect, 0f, 360f, false, track)
        canvas.drawArc(rect, -90f, 360f * shown, false, arc)
        label.textSize = width * 0.24f
        canvas.drawText("$value/$total", width / 2f, height / 2f + label.textSize * 0.36f, label)
    }
}

/** Rounded gradient slider (0–100) used for brightness. [onChange] fires while dragging,
 *  [onCommit] once on release. */
@SuppressLint("ClickableViewAccessibility")
class GradientSlider(ctx: Context, private val p: Palette) : View(ctx) {
    var value = 50
        set(v) { field = v.coerceIn(0, 100); invalidate() }
    var onChange: ((Int) -> Unit)? = null
    var onCommit: ((Int) -> Unit)? = null
    private val bg = Paint(Paint.ANTI_ALIAS_FLAG)
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val txt = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; textAlign = Paint.Align.LEFT }
    private val r = RectF()

    override fun onDraw(canvas: Canvas) {
        val h = height.toFloat()
        r.set(0f, 0f, width.toFloat(), h)
        bg.color = withAlpha(p.text, 0.08f)
        canvas.drawRoundRect(r, h / 2, h / 2, bg)
        val fw = max(h, width * value / 100f)
        fill.shader = LinearGradient(0f, 0f, fw, 0f, p.c1, p.c2, Shader.TileMode.CLAMP)
        r.set(0f, 0f, fw, h)
        canvas.drawRoundRect(r, h / 2, h / 2, fill)
        txt.textSize = h * 0.45f
        canvas.drawText("☀  $value%", h * 0.4f, h / 2 + txt.textSize * 0.36f, txt)
    }

    override fun onTouchEvent(e: MotionEvent): Boolean {
        if (!isEnabled) return false
        val v = ((e.x / width) * 100).toInt().coerceIn(0, 100)
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> { parent?.requestDisallowInterceptTouchEvent(true); value = v; onChange?.invoke(v) }
            MotionEvent.ACTION_MOVE -> { value = v; onChange?.invoke(v) }
            MotionEvent.ACTION_UP -> { value = v; onChange?.invoke(v); onCommit?.invoke(v) }
            MotionEvent.ACTION_CANCEL -> onCommit?.invoke(value)
        }
        return true
    }
}

/**
 * Hold-to-confirm row for destructive admin actions (exit kiosk, uninstall): the background
 * fills over [holdMs] while pressed; releasing early cancels. Stops a stray tap from ever
 * exiting kiosk.
 */
@SuppressLint("ClickableViewAccessibility")
class HoldToConfirm(
    ctx: Context,
    private val p: Palette,
    private val holdMs: Long = 1200,
    private val onConfirm: () -> Unit,
) : androidx.appcompat.widget.AppCompatTextView(ctx) {
    private var progress = 0f
    private var anim: ValueAnimator? = null
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)

    override fun onDraw(canvas: Canvas) {
        if (progress > 0f) {
            fill.color = withAlpha(p.alert, 0.18f)
            canvas.drawRect(0f, 0f, width * progress, height.toFloat(), fill)
        }
        super.onDraw(canvas)
    }

    override fun onTouchEvent(e: MotionEvent): Boolean {
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                anim?.cancel()
                anim = ValueAnimator.ofFloat(0f, 1f).apply {
                    duration = holdMs
                    interpolator = LinearInterpolator()
                    addUpdateListener {
                        progress = it.animatedValue as Float
                        invalidate()
                        if (progress >= 1f) {
                            cancel()
                            performHapticFeedback(android.view.HapticFeedbackConstants.LONG_PRESS)
                            onConfirm()
                        }
                    }
                    start()
                }
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                anim?.cancel()
                progress = 0f
                invalidate()
            }
        }
        return true
    }
}

// --- Client branding -------------------------------------------------------------------------------

/**
 * Decodes a cached client logo for display: downsampled (longest side around [maxPx] * 2, so the
 * trimmed artwork stays sharp) and with fully transparent borders cropped away. Logos are often
 * exported on a large square canvas with generous empty margins; without the crop the artwork
 * would occupy only a fraction of the space it is given.
 */
fun loadBrandBitmap(file: java.io.File?, maxPx: Int): android.graphics.Bitmap? {
    if (file == null) return null
    return runCatching {
        val bounds = android.graphics.BitmapFactory.Options().apply { inJustDecodeBounds = true }
        android.graphics.BitmapFactory.decodeFile(file.path, bounds)
        val target = maxPx * 2
        var sample = 1
        while (max(bounds.outWidth, bounds.outHeight) / (sample * 2) >= target) sample *= 2
        val decoded = android.graphics.BitmapFactory.decodeFile(
            file.path,
            android.graphics.BitmapFactory.Options().apply { inSampleSize = sample },
        ) ?: return@runCatching null
        trimTransparent(decoded)
    }.getOrNull()
}

/** Crops [src] to the bounding box of its visible (non-transparent) pixels; returns [src] if none. */
private fun trimTransparent(src: android.graphics.Bitmap): android.graphics.Bitmap {
    if (!src.hasAlpha()) return src
    val w = src.width
    val h = src.height
    val px = IntArray(w * h)
    src.getPixels(px, 0, w, 0, 0, w, h)
    var minX = w
    var minY = h
    var maxX = -1
    var maxY = -1
    for (y in 0 until h) {
        val row = y * w
        for (x in 0 until w) {
            if ((px[row + x] ushr 24) > 24) {
                if (x < minX) minX = x
                if (x > maxX) maxX = x
                if (y < minY) minY = y
                if (y > maxY) maxY = y
            }
        }
    }
    if (maxX < minX || maxY < minY) return src
    // Small breathing margin so anti-aliased edges are not clipped.
    val pad = 2
    minX = (minX - pad).coerceAtLeast(0); minY = (minY - pad).coerceAtLeast(0)
    maxX = (maxX + pad).coerceAtMost(w - 1); maxY = (maxY + pad).coerceAtMost(h - 1)
    if (minX == 0 && minY == 0 && maxX == w - 1 && maxY == h - 1) return src
    return android.graphics.Bitmap.createBitmap(src, minX, minY, maxX - minX + 1, maxY - minY + 1)
}
