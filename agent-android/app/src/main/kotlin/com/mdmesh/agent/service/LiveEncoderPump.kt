package com.mdmesh.agent.service

import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.Surface
import com.mdmesh.core.remote.LiveFrameUploader
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong

/**
 * Hardware H.264 encoder fed through an input [Surface] (from a VirtualDisplay or a camera), plus the
 * batching uploader for one live stream of [kind] (`screen | cameraFront | cameraBack`).
 *
 * Packet framing: type(1: 1=config, 2=key, 3=delta, 4=meta JSON) | ptsUs(8, BE) | length(4, BE) | payload.
 * Packets are uploaded in ~33 ms batches. If the uplink backs up, queued video is dropped and a fresh
 * keyframe requested instead of letting latency grow.
 */
class LiveEncoderPump(
    private val kind: String,
    private val uploader: LiveFrameUploader,
    private val fps: Int,
    private val bitrate: Int,
) {
    private var encoder: MediaCodec? = null
    private var input: Surface? = null
    private val queue = ConcurrentLinkedQueue<ByteArray>()
    private val queuedBytes = AtomicLong(0)
    private val needKey = AtomicBoolean(false)
    private val info = MediaCodec.BufferInfo()
    private var sender: Job? = null
    private var statFrames = 0
    private var statBytes = 0L
    private var statSince = System.currentTimeMillis()
    private var statUploadFail = 0

    /** Creates and starts the encoder; returns the surface the video source must render into. */
    fun open(w: Int, h: Int): Surface {
        fun format(hints: Boolean) = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, w, h).apply {
            setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
            setInteger(MediaFormat.KEY_BIT_RATE, bitrate)
            setInteger(MediaFormat.KEY_FRAME_RATE, fps)
            setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1)
            // A static scene produces no new frames; repeat the last one so the stream never stalls.
            setLong(MediaFormat.KEY_REPEAT_PREVIOUS_FRAME_AFTER, 100_000L)
            setInteger("prepend-sps-pps-to-idr-frames", 1)
            if (hints) {
                setInteger(MediaFormat.KEY_BITRATE_MODE, MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    setInteger(MediaFormat.KEY_PRIORITY, 0)
                    setInteger(MediaFormat.KEY_OPERATING_RATE, fps)
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) setInteger(MediaFormat.KEY_LATENCY, 1)
                setInteger("max-fps-to-encoder", fps) // 90/120 Hz displays must not overfeed the encoder
            }
        }
        var enc = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
        try {
            enc.configure(format(true), null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        } catch (e: Exception) {
            // Some encoders reject the hints - retry with the bare minimum on a fresh codec.
            runCatching { enc.release() }
            enc = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
            enc.configure(format(false), null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        }
        val surface = enc.createInputSurface()
        enc.start()
        encoder = enc
        input = surface
        return surface
    }

    fun close() {
        runCatching { encoder?.stop() }
        runCatching { encoder?.release() }
        runCatching { input?.release() }
        encoder = null
        input = null
    }

    fun startSender(scope: CoroutineScope) {
        sender = scope.launch(Dispatchers.IO) {
            val batch = ByteArrayOutputStream(64 * 1024)
            while (isActive) {
                delay(BATCH_MS)
                batch.reset()
                while (true) {
                    val p = queue.poll() ?: break
                    queuedBytes.addAndGet(-p.size.toLong())
                    batch.write(p)
                }
                if (batch.size() == 0) continue
                val ok = runCatching { uploader.upload(kind, batch.toByteArray()) }.getOrDefault(false)
                if (!ok) { statUploadFail++; requestKeyframe() } // what was lost is undecodable: restart from a keyframe
            }
        }
    }

    fun meta(json: String) {
        val framed = frame(4, 0, json.toByteArray())
        queue.add(framed)
        queuedBytes.addAndGet(framed.size.toLong())
    }

    private fun requestKeyframe() {
        needKey.set(true)
        runCatching { encoder?.setParameters(Bundle().apply { putInt(MediaCodec.PARAMETER_KEY_REQUEST_SYNC_FRAME, 0) }) }
    }

    /** Pulls at most one encoded buffer (waits up to 10 ms) and queues it for upload. */
    fun drainOnce() {
        val enc = encoder ?: return
        val idx = runCatching { enc.dequeueOutputBuffer(info, 10_000L) }.getOrDefault(-1)
        if (idx < 0) return
        val buf: ByteBuffer? = runCatching { enc.getOutputBuffer(idx) }.getOrNull()
        if (buf != null && info.size > 0) {
            val isConfig = info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0
            val isKey = info.flags and MediaCodec.BUFFER_FLAG_KEY_FRAME != 0
            if (isKey) needKey.set(false)
            if (isConfig || isKey || !needKey.get()) {
                val payload = ByteArray(info.size)
                buf.position(info.offset); buf.limit(info.offset + info.size); buf.get(payload)
                val type = if (isConfig) 1 else if (isKey) 2 else 3
                if (!isConfig) { statFrames++; statBytes += payload.size }
                val framed = frame(type, info.presentationTimeUs, payload)
                queue.add(framed)
                if (queuedBytes.addAndGet(framed.size.toLong()) > MAX_BACKLOG) {
                    queue.clear(); queuedBytes.set(0)
                    requestKeyframe()
                }
            }
        }
        runCatching { enc.releaseOutputBuffer(idx, false) }
        sendStatsIfDue()
    }

    /** Every 2 s tell the console what the encoder is really producing, so a stall can be located. */
    private fun sendStatsIfDue() {
        val now = System.currentTimeMillis()
        if (now - statSince < 2000) return
        val secs = (now - statSince) / 1000.0
        val json = """{"enc_fps":${"%.1f".format(java.util.Locale.US, statFrames / secs)},"kbps":${(statBytes * 8 / 1000 / secs).toInt()},"backlog_kb":${queuedBytes.get() / 1024},"upload_fail":$statUploadFail}"""
        Log.i("LiveEncoderPump", "$kind $json")
        meta(json)
        statFrames = 0; statBytes = 0; statSince = now
    }

    fun stop() {
        sender?.cancel()
        close()
    }

    private fun frame(type: Int, ptsUs: Long, payload: ByteArray): ByteArray {
        val out = ByteBuffer.allocate(13 + payload.size)
        out.put(type.toByte()).putLong(ptsUs).putInt(payload.size).put(payload)
        return out.array()
    }

    private companion object {
        const val BATCH_MS = 33L
        const val MAX_BACKLOG = 4_000_000L
    }
}
