package com.mdmesh.agent.battery

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.MediaPlayer
import android.media.ToneGenerator
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.util.Log
import com.mdmesh.core.battery.BatteryStage
import java.util.Locale

/**
 * Plays the battery warning: an error tone, then the voice note "Battery low, charge now" (English, then Hindi).
 *
 * - Always at 50% of the alarm volume, whether the tablet is muted or not; the previous alarm volume is put back afterwards.
 * - The voice is the recorded file `res/raw/battery_low_voice` when the app contains one. Until a recording is supplied it falls
 *   back to the tablet's text-to-speech voices (English and Hindi, each only if installed).
 * - Never plays while the screen is off; the caller decides that.
 */
class BatteryAlertPlayer(private val context: Context) {
    private val main = Handler(Looper.getMainLooper())
    private val audio = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private var tts: TextToSpeech? = null
    private var busy = false

    @Synchronized
    fun play(stage: BatteryStage) {
        if (busy || stage == BatteryStage.NORMAL) return
        busy = true
        val previous = runCatching { audio.getStreamVolume(AudioManager.STREAM_ALARM) }.getOrDefault(-1)
        val half = (audio.getStreamMaxVolume(AudioManager.STREAM_ALARM) / 2).coerceAtLeast(1)
        runCatching { audio.setStreamVolume(AudioManager.STREAM_ALARM, half, 0) }
        val finish = {
            if (previous >= 0) runCatching { audio.setStreamVolume(AudioManager.STREAM_ALARM, previous, 0) }
            busy = false
        }
        runCatching { tone(stage) }.onFailure { Log.w(TAG, "tone failed", it) }
        // Let the tone finish, then speak.
        main.postDelayed({ voice(finish) }, if (stage == BatteryStage.RED) 1700L else 1100L)
    }

    private fun tone(stage: BatteryStage) {
        val gen = ToneGenerator(AudioManager.STREAM_ALARM, 100)
        when (stage) {
            BatteryStage.YELLOW -> gen.startTone(ToneGenerator.TONE_PROP_BEEP2, 600)
            BatteryStage.ORANGE -> gen.startTone(ToneGenerator.TONE_SUP_ERROR, 900)
            else -> gen.startTone(ToneGenerator.TONE_CDMA_EMERGENCY_RINGBACK, 1500)
        }
        main.postDelayed({ runCatching { gen.release() } }, 2000L)
    }

    private fun voice(done: () -> Unit) {
        val resId = context.resources.getIdentifier(VOICE_RES, "raw", context.packageName)
        if (resId != 0) playFile(resId, done) else speak(done)
    }

    private fun playFile(resId: Int, done: () -> Unit) {
        runCatching {
            val mp = MediaPlayer.create(
                context, resId,
                AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build(),
                audio.generateAudioSessionId(),
            )
            if (mp == null) { done(); return }
            mp.setOnCompletionListener { it.release(); done() }
            mp.setOnErrorListener { p, _, _ -> p.release(); done(); true }
            mp.start()
        }.onFailure { Log.w(TAG, "voice file failed", it); done() }
    }

    private fun speak(done: () -> Unit) {
        var engine: TextToSpeech? = null
        engine = TextToSpeech(context) { status ->
            val e = engine
            if (status != TextToSpeech.SUCCESS || e == null) { done(); return@TextToSpeech }
            runCatching {
                e.setAudioAttributes(
                    AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build(),
                )
                val params = android.os.Bundle().apply { putInt(TextToSpeech.Engine.KEY_PARAM_STREAM, AudioManager.STREAM_ALARM) }
                var queued = 0
                if (e.isLanguageAvailable(Locale.ENGLISH) >= TextToSpeech.LANG_AVAILABLE) {
                    e.language = Locale.ENGLISH
                    e.speak("Battery low. Charge now.", TextToSpeech.QUEUE_ADD, params, "en"); queued++
                }
                val hindi = Locale("hi", "IN")
                if (e.isLanguageAvailable(hindi) >= TextToSpeech.LANG_AVAILABLE) {
                    e.language = hindi
                    e.speak("बैटरी कम है। अभी चार्ज करें।", TextToSpeech.QUEUE_ADD, params, "hi"); queued++
                }
                e.setOnUtteranceProgressListener(object : android.speech.tts.UtteranceProgressListener() {
                    var left = queued
                    override fun onStart(utteranceId: String?) = Unit
                    override fun onDone(utteranceId: String?) { if (--left <= 0) main.post { e.shutdown(); done() } }
                    @Deprecated("Deprecated in Java")
                    override fun onError(utteranceId: String?) { main.post { e.shutdown(); done() } }
                })
                if (queued == 0) { e.shutdown(); done() }
            }.onFailure { Log.w(TAG, "speech failed", it); done() }
        }
        tts = engine
    }

    private companion object {
        const val TAG = "BatteryAlert"
        /** Drop a recording at app/src/main/res/raw/battery_low_voice.(mp3|ogg|wav) and it is used automatically. */
        const val VOICE_RES = "battery_low_voice"
    }
}
