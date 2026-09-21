package com.mdmesh.agent.ime

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.inputmethodservice.InputMethodService
import android.media.AudioManager
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import com.mdmesh.agent.R

/**
 * Enterprise Capital-Only Keyboard (IME) for AMBIC MDM.
 *
 * Emits strictly uppercase characters directly into the InputConnection at keystroke
 * time. Eliminates accessibility-based post-commit text mutations, cursor jumping,
 * composition conflicts, and service crashes.
 */
class CapsKeyboardService : InputMethodService() {

    private var rootLayout: LinearLayout? = null
    private var actionButton: Button? = null
    private var isSymbolsMode = false

    private val handler = Handler(Looper.getMainLooper())
    private var backspaceRunnable: Runnable? = null
    private var audioManager: AudioManager? = null

    override fun onCreate() {
        super.onCreate()
        audioManager = getSystemService(Context.AUDIO_SERVICE) as? AudioManager
    }

    override fun onCreateInputView(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#0B0F17"))
            val padH = dp(4)
            val padV = dp(6)
            setPadding(padH, padV, padH, padV)
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
        }
        rootLayout = root
        renderKeyboard()
        return root
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        isSymbolsMode = false
        renderKeyboard()
        updateActionButton(info)
    }

    private fun renderKeyboard() {
        val root = rootLayout ?: return
        root.removeAllViews()

        val rowHeight = dp(52)

        // Row 0: Top Numbers Row (Permanent for fast jewellery/inventory billing)
        val numRow = createRow(rowHeight)
        val numbers = arrayOf("1", "2", "3", "4", "5", "6", "7", "8", "9", "0")
        for (num in numbers) {
            numRow.addView(createKeyButton(num, 1.0f) { commitKey(num) })
        }
        root.addView(numRow)

        if (!isSymbolsMode) {
            renderLettersLayout(root, rowHeight)
        } else {
            renderSymbolsLayout(root, rowHeight)
        }
    }

    private fun renderLettersLayout(root: LinearLayout, rowHeight: Int) {
        // Row 1: Q W E R T Y U I O P
        val r1 = createRow(rowHeight)
        val keys1 = arrayOf("Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P")
        for (k in keys1) {
            r1.addView(createKeyButton(k, 1.0f) { commitKey(k) })
        }
        root.addView(r1)

        // Row 2: A S D F G H J K L (centered)
        val r2 = createRow(rowHeight)
        r2.addView(createSpacer(0.5f))
        val keys2 = arrayOf("A", "S", "D", "F", "G", "H", "J", "K", "L")
        for (k in keys2) {
            r2.addView(createKeyButton(k, 1.0f) { commitKey(k) })
        }
        r2.addView(createSpacer(0.5f))
        root.addView(r2)

        // Row 3: ?123, Z X C V B N M, Backspace
        val r3 = createRow(rowHeight)
        r3.addView(createControlKey("?123", 1.5f) {
            isSymbolsMode = true
            renderKeyboard()
        })
        val keys3 = arrayOf("Z", "X", "C", "V", "B", "N", "M")
        for (k in keys3) {
            r3.addView(createKeyButton(k, 1.0f) { commitKey(k) })
        }
        r3.addView(createBackspaceKey(1.5f))
        root.addView(r3)

        // Row 4: TAB, Comma, SPACE, Period, ACTION
        val r4 = createRow(rowHeight)
        r4.addView(createControlKey("TAB", 1.5f) { handleTab() })
        r4.addView(createKeyButton(",", 1.0f) { commitKey(",") })
        r4.addView(createKeyButton("SPACE", 5.0f) { commitKey(" ") })
        r4.addView(createKeyButton(".", 1.0f) { commitKey(".") })
        val actionBtn = createActionKey(1.5f)
        actionButton = actionBtn
        r4.addView(actionBtn)
        root.addView(r4)

        updateActionButton(currentInputEditorInfo)
    }

    private fun renderSymbolsLayout(root: LinearLayout, rowHeight: Int) {
        // Row 1: @ # ₹ $ % & * - + _
        val r1 = createRow(rowHeight)
        val keys1 = arrayOf("@", "#", "₹", "$", "%", "&", "*", "-", "+", "_")
        for (k in keys1) {
            r1.addView(createKeyButton(k, 1.0f) { commitKey(k) })
        }
        root.addView(r1)

        // Row 2: ( ) / \ : ; " ' =
        val r2 = createRow(rowHeight)
        r2.addView(createSpacer(0.5f))
        val keys2 = arrayOf("(", ")", "/", "\\", ":", ";", "\"", "'", "=")
        for (k in keys2) {
            r2.addView(createKeyButton(k, 1.0f) { commitKey(k) })
        }
        r2.addView(createSpacer(0.5f))
        root.addView(r2)

        // Row 3: ABC, ! ? < > [ ] ~, Backspace
        val r3 = createRow(rowHeight)
        r3.addView(createControlKey("ABC", 1.5f) {
            isSymbolsMode = false
            renderKeyboard()
        })
        val keys3 = arrayOf("!", "?", "<", ">", "[", "]", "~")
        for (k in keys3) {
            r3.addView(createKeyButton(k, 1.0f) { commitKey(k) })
        }
        r3.addView(createBackspaceKey(1.5f))
        root.addView(r3)

        // Row 4: TAB, Comma, SPACE, Period, ACTION
        val r4 = createRow(rowHeight)
        r4.addView(createControlKey("TAB", 1.5f) { handleTab() })
        r4.addView(createKeyButton(",", 1.0f) { commitKey(",") })
        r4.addView(createKeyButton("SPACE", 5.0f) { commitKey(" ") })
        r4.addView(createKeyButton(".", 1.0f) { commitKey(".") })
        val actionBtn = createActionKey(1.5f)
        actionButton = actionBtn
        r4.addView(actionBtn)
        root.addView(r4)

        updateActionButton(currentInputEditorInfo)
    }

    private fun commitKey(text: String) {
        feedbackTap()
        currentInputConnection?.commitText(text.uppercase(), 1)
    }

    private fun handleTab() {
        feedbackTap()
        sendDownUpKeyEvents(KeyEvent.KEYCODE_TAB)
    }

    private fun handleAction() {
        feedbackTap()
        val info = currentInputEditorInfo
        val ic = currentInputConnection ?: return
        val action = (info?.imeOptions ?: 0) and EditorInfo.IME_MASK_ACTION
        when (action) {
            EditorInfo.IME_ACTION_NONE, EditorInfo.IME_ACTION_UNSPECIFIED -> {
                sendDownUpKeyEvents(KeyEvent.KEYCODE_ENTER)
            }
            else -> {
                ic.performEditorAction(action)
            }
        }
    }

    private fun handleBackspaceOnce() {
        feedbackTap()
        val ic = currentInputConnection ?: return
        val selected = ic.getSelectedText(0)
        if (!selected.isNullOrEmpty()) {
            ic.commitText("", 1)
        } else {
            ic.deleteSurroundingText(1, 0)
        }
    }

    private fun updateActionButton(info: EditorInfo?) {
        val btn = actionButton ?: return
        val action = (info?.imeOptions ?: 0) and EditorInfo.IME_MASK_ACTION
        val label = when (action) {
            EditorInfo.IME_ACTION_GO -> "GO"
            EditorInfo.IME_ACTION_SEARCH -> "FIND"
            EditorInfo.IME_ACTION_SEND -> "SEND"
            EditorInfo.IME_ACTION_NEXT -> "NEXT"
            EditorInfo.IME_ACTION_DONE -> "DONE"
            else -> "ENTER"
        }
        btn.text = label
    }

    private fun feedbackTap() {
        runCatching {
            rootLayout?.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            audioManager?.playSoundEffect(AudioManager.FX_KEYPRESS_STANDARD)
        }
    }

    private fun createRow(height: Int): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                height
            ).apply {
                val marginV = dp(2)
                setMargins(0, marginV, 0, marginV)
            }
        }
    }

    private fun createSpacer(weight: Float): View {
        return View(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, weight)
        }
    }

    private fun createKeyButton(label: String, weight: Float, onClick: () -> Unit): Button {
        return Button(this).apply {
            text = label
            textSize = 17f
            setTextColor(Color.parseColor("#F3F5F8"))
            typeface = Typeface.DEFAULT_BOLD
            isAllCaps = false
            background = ContextCompat.getDrawable(this@CapsKeyboardService, R.drawable.bg_keyboard_key)
            val marginH = dp(2)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, weight).apply {
                setMargins(marginH, 0, marginH, 0)
            }
            setPadding(0, 0, 0, 0)
            setOnClickListener { onClick() }
        }
    }

    private fun createControlKey(label: String, weight: Float, onClick: () -> Unit): Button {
        return Button(this).apply {
            text = label
            textSize = 14f
            setTextColor(Color.parseColor("#8992A0"))
            typeface = Typeface.DEFAULT_BOLD
            isAllCaps = false
            background = ContextCompat.getDrawable(this@CapsKeyboardService, R.drawable.bg_keyboard_key_ctrl)
            val marginH = dp(2)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, weight).apply {
                setMargins(marginH, 0, marginH, 0)
            }
            setPadding(0, 0, 0, 0)
            setOnClickListener { onClick() }
        }
    }

    private fun createActionKey(weight: Float): Button {
        return Button(this).apply {
            text = "ENTER"
            textSize = 14f
            setTextColor(Color.WHITE)
            typeface = Typeface.DEFAULT_BOLD
            isAllCaps = true
            background = ContextCompat.getDrawable(this@CapsKeyboardService, R.drawable.bg_keyboard_key_action)
            val marginH = dp(2)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, weight).apply {
                setMargins(marginH, 0, marginH, 0)
            }
            setPadding(0, 0, 0, 0)
            setOnClickListener { handleAction() }
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun createBackspaceKey(weight: Float): Button {
        val btn = Button(this).apply {
            text = "⌫"
            textSize = 18f
            setTextColor(Color.parseColor("#FF6B6B"))
            typeface = Typeface.DEFAULT_BOLD
            background = ContextCompat.getDrawable(this@CapsKeyboardService, R.drawable.bg_keyboard_key_ctrl)
            val marginH = dp(2)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, weight).apply {
                setMargins(marginH, 0, marginH, 0)
            }
            setPadding(0, 0, 0, 0)
        }

        btn.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    handleBackspaceOnce()
                    startBackspaceRepeat()
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    stopBackspaceRepeat()
                    true
                }
                else -> false
            }
        }
        return btn
    }

    private fun startBackspaceRepeat() {
        stopBackspaceRepeat()
        val repeatRunnable = object : Runnable {
            override fun run() {
                handleBackspaceOnce()
                handler.postDelayed(this, 60)
            }
        }
        backspaceRunnable = repeatRunnable
        handler.postDelayed(repeatRunnable, 350)
    }

    private fun stopBackspaceRepeat() {
        backspaceRunnable?.let { handler.removeCallbacks(it) }
        backspaceRunnable = null
    }

    private fun dp(value: Int): Int {
        val scale = resources.displayMetrics.density
        return (value * scale + 0.5f).toInt()
    }

    override fun onDestroy() {
        stopBackspaceRepeat()
        super.onDestroy()
    }
}
