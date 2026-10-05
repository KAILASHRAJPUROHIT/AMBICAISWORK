package com.mdmesh.agent.update

import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import com.mdmesh.core.update.UpdateConsentCoordinator
import com.mdmesh.core.update.UpdateConsentCoordinator.Choice
import com.mdmesh.core.update.UpdateConsentStore
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

/**
 * The 60-second "MDM update queued" popup, English over Hindi, with **Update now** and **Update later**.
 * No answer by the deadline counts as Update now. Back is disabled so the question is always answered.
 * The text and the deadline come from [UpdateConsentStore], so a re-created screen keeps counting from the same moment.
 */
@AndroidEntryPoint
class UpdateConsentActivity : ComponentActivity() {

    @Inject lateinit var coordinator: UpdateConsentCoordinator
    @Inject lateinit var store: UpdateConsentStore

    private val ui = Handler(Looper.getMainLooper())
    private lateinit var countdownEn: TextView
    private lateinit var countdownHi: TextView
    private var deadline = 0L
    private var answered = false

    private val ticker = object : Runnable {
        override fun run() {
            val left = ((deadline - System.currentTimeMillis() + 999) / 1000).coerceAtLeast(0)
            countdownEn.text = "Updating automatically in $left seconds"
            countdownHi.text = "$left सेकंड में अपने-आप अपडेट होगा"
            if (left <= 0L) answer(Choice.TIMEOUT) else ui.postDelayed(this, 250L)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val p = store.get()
        if (p == null || p.state != UpdateConsentStore.State.WAITING) { finish(); return }
        deadline = p.offerDeadline
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) { setShowWhenLocked(true); setTurnScreenOn(true) }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) { override fun handleOnBackPressed() = Unit })
        setContentView(buildUi(mandatory = p.mandatory))
    }

    override fun onResume() {
        super.onResume()
        ui.removeCallbacks(ticker)
        ui.post(ticker)
    }

    override fun onPause() {
        ui.removeCallbacks(ticker)
        super.onPause()
    }

    private fun answer(choice: Choice) {
        if (answered) return
        answered = true
        ui.removeCallbacks(ticker)
        coordinator.onChoice(choice)
        finish()
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()
    private val isPhone: Boolean get() = resources.configuration.smallestScreenWidthDp < 600

    private fun text(s: String, sp: Float, color: Int, bold: Boolean = false, center: Boolean = true) = TextView(this).apply {
        text = s
        textSize = sp
        setTextColor(color)
        if (bold) setTypeface(typeface, Typeface.BOLD)
        if (center) gravity = Gravity.CENTER
    }

    private fun button(en: String, hi: String, fill: Int, fg: Int, onClick: () -> Unit) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER
        setPadding(dp(16), dp(12), dp(16), dp(12))
        background = GradientDrawable().apply { setColor(fill); cornerRadius = dp(14).toFloat() }
        isClickable = true
        isFocusable = true
        addView(text(en, 17f, fg, bold = true))
        addView(text(hi, 15f, fg))
        setOnClickListener { onClick() }
    }

    private fun buildUi(mandatory: Boolean): View {
        val bg = Color.parseColor("#0E1420")
        val card = Color.parseColor("#182234")
        val ink = Color.parseColor("#F2F5FA")
        val dim = Color.parseColor("#A9B4C6")
        val accent = Color.parseColor("#4C8DFF")

        val body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(if (isPhone) 20 else 36), dp(if (isPhone) 22 else 32), dp(if (isPhone) 20 else 36), dp(if (isPhone) 22 else 32))
            background = GradientDrawable().apply { setColor(card); cornerRadius = dp(22).toFloat() }
        }
        body.addView(text("MDM update queued", if (isPhone) 22f else 28f, ink, bold = true))
        body.addView(text("Your current app will close and re-open to finish the update.", 16f, dim).apply { setPadding(0, dp(6), 0, dp(14)) })
        body.addView(View(this).apply { setBackgroundColor(Color.parseColor("#2C3A52")); layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)) })
        body.addView(text("MDM अपडेट कतार में है", if (isPhone) 22f else 28f, ink, bold = true).apply { setPadding(0, dp(14), 0, 0) })
        body.addView(text("अपडेट पूरा करने के लिए आपका मौजूदा ऐप बंद होकर फिर से खुलेगा।", 16f, dim).apply { setPadding(0, dp(6), 0, dp(16)) })

        countdownEn = text("", 14f, accent, bold = true)
        countdownHi = text("", 14f, accent, bold = true)
        body.addView(countdownEn)
        body.addView(countdownHi.apply { setPadding(0, dp(2), 0, dp(14)) })

        if (mandatory) {
            body.addView(text("This update is required.  /  यह अपडेट आवश्यक है।", 13f, Color.parseColor("#FFB14D")).apply { setPadding(0, 0, 0, dp(12)) })
        }

        val buttons = LinearLayout(this).apply { orientation = if (isPhone) LinearLayout.VERTICAL else LinearLayout.HORIZONTAL }
        val lp = { LinearLayout.LayoutParams(if (isPhone) ViewGroup.LayoutParams.MATCH_PARENT else 0, ViewGroup.LayoutParams.WRAP_CONTENT, if (isPhone) 0f else 1f).apply { setMargins(dp(6), dp(6), dp(6), dp(6)) } }
        if (!mandatory) {
            buttons.addView(button("Update later", "बाद में अपडेट करें", Color.parseColor("#2C3A52"), ink) { answer(Choice.LATER) }, lp())
        }
        buttons.addView(button("Update now", "अभी अपडेट करें", accent, Color.WHITE) { answer(Choice.NOW) }, lp())
        body.addView(buttons, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))

        val root = LinearLayout(this).apply {
            gravity = Gravity.CENTER
            setBackgroundColor(bg)
            setPadding(dp(16), dp(16), dp(16), dp(16))
            addView(body, LinearLayout.LayoutParams(if (isPhone) ViewGroup.LayoutParams.MATCH_PARENT else dp(560), ViewGroup.LayoutParams.WRAP_CONTENT))
        }
        return ScrollView(this).apply {
            isFillViewport = true
            setBackgroundColor(bg)
            addView(root, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        }
    }
}
