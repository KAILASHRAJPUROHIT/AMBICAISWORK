package com.mdmesh.core.remote

import android.annotation.SuppressLint
import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import android.util.Log
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.delay
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/** Short AAC audio clip capture — like [RemoteCameraCapture], a bounded one-shot, not continuous
 *  live audio. Requires RECORD_AUDIO already granted (silently, Device-Owner-only). Android's mic-
 *  in-use indicator will show while [clipSeconds] elapses — unavoidable, by design, same as the
 *  camera capture. */
@Singleton
class RemoteMicCapture @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private companion object {
        const val TAG = "RemoteMicCapture"
    }

    @SuppressLint("MissingPermission") // caller-verified: only invoked when RECORD_AUDIO is granted
    suspend fun captureAac(clipSeconds: Int = 6): ByteArray? {
        val out = File(context.cacheDir, "mdm-remote-mic-${System.nanoTime()}.m4a")
        @Suppress("DEPRECATION")
        val recorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) MediaRecorder(context) else MediaRecorder()
        return try {
            recorder.apply {
                setAudioSource(MediaRecorder.AudioSource.MIC)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setAudioEncodingBitRate(64_000)
                setAudioSamplingRate(44_100)
                setOutputFile(out.absolutePath)
                prepare()
                start()
            }
            delay(clipSeconds * 1000L)
            runCatching { recorder.stop() }
            out.takeIf { it.exists() && it.length() > 0 }?.readBytes()
                ?: run { Log.w(TAG, "mic clip empty or missing (exists=${out.exists()}, len=${out.length()})"); null }
        } catch (e: Exception) {
            Log.w(TAG, "mic capture threw", e)
            null
        } finally {
            runCatching { recorder.release() }
            out.delete()
        }
    }
}
