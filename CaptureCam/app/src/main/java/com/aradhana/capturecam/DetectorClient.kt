package com.aradhana.capturecam

import android.util.Log
import kotlinx.coroutines.Runnable
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/**
 * Persistent WebSocket connection to detector_server.py (the laptop's
 * Grounding DINO "eyes"). Fire-and-forget frame sending, async detection
 * callbacks -- this class never blocks the caller waiting for a response,
 * matching the "never queue frames" design: the SERVER discards stale
 * frames on its end, and staleness of the RESPONSE (how old the detection
 * is by the time it arrives) is judged by the caller using
 * DetectionResult.ageMs(), not by anything blocking here.
 */
class DetectorClient(private val onDetection: (DetectionResult) -> Unit) {

    data class DetectionResult(
        val frameId: Int,
        val captureTimestamp: Long,
        val detected: Boolean,
        val x: Float, val y: Float, val w: Float, val h: Float,
        val serverLatencyMs: Double,
    ) {
        /** How old this detection is RIGHT NOW, in ms -- the network+
         * inference round trip time. Staleness tiers per spec: <150ms
         * usable directly, 150-300ms correction-only, >300ms discard. */
        fun ageMs(): Long = System.currentTimeMillis() - captureTimestamp
    }

    private val client = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.SECONDS) // long-lived socket, no read timeout
        .build()

    private var webSocket: WebSocket? = null
    private val frameIdCounter = AtomicInteger(0)
    @Volatile var isConnected: Boolean = false
        private set
    @Volatile private var lastSendAt = 0L
    private var reconnectHandler: android.os.Handler? = null
    private var wsUrl: String = ""
    private var stopped = true

    /** Minimum gap between frames actually sent -- client-side throttle so
     * we're not JPEG-encoding and pushing bytes over the network far
     * faster than the server could ever consume them anyway (it's ~300ms/
     * detection warm). The server's own drop-stale logic is the real
     * safety net; this just avoids wasted encode/network work. */
    private val minSendIntervalMs = 100L

    fun connect(url: String) {
        wsUrl = url
        stopped = false
        openSocket()
    }

    private fun openSocket() {
        if (stopped) return
        Log.i(TAG, "Connecting to $wsUrl")
        val request = Request.Builder().url(wsUrl).build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.i(TAG, "Detector WebSocket connected")
                isConnected = true
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val json = JSONObject(text)
                    val result = DetectionResult(
                        frameId = json.getInt("frame_id"),
                        captureTimestamp = json.getLong("capture_timestamp"),
                        detected = json.optBoolean("detected", false),
                        x = json.optDouble("x", 0.0).toFloat(),
                        y = json.optDouble("y", 0.0).toFloat(),
                        w = json.optDouble("w", 0.0).toFloat(),
                        h = json.optDouble("h", 0.0).toFloat(),
                        serverLatencyMs = json.optDouble("server_latency_ms", 0.0),
                    )
                    onDetection(result)
                } catch (e: Exception) {
                    Log.w(TAG, "Bad detection message: ${e.message}")
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.w(TAG, "Detector WebSocket failed: ${t.message}")
                isConnected = false
                scheduleReconnect()
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "Detector WebSocket closed: $code $reason")
                isConnected = false
                scheduleReconnect()
            }
        })
    }

    private fun scheduleReconnect() {
        if (stopped) return
        if (reconnectHandler == null) reconnectHandler = android.os.Handler(android.os.Looper.getMainLooper())
        reconnectHandler?.postDelayed({ if (!stopped) openSocket() }, 2000L)
    }

    /** Sends one frame if the throttle allows and the socket is open.
     * Fire-and-forget -- returns immediately, the response (if any)
     * arrives later via onDetection. Returns the frame_id assigned, or -1
     * if the frame was skipped (throttled or not connected). */
    fun sendFrame(jpeg: ByteArray): Int {
        val ws = webSocket ?: return -1
        if (!isConnected) return -1
        val now = System.currentTimeMillis()
        if (now - lastSendAt < minSendIntervalMs) return -1
        lastSendAt = now
        val frameId = frameIdCounter.incrementAndGet()
        val json = JSONObject().apply {
            put("frame_id", frameId)
            put("timestamp", now)
            put("jpeg_b64", android.util.Base64.encodeToString(jpeg, android.util.Base64.NO_WRAP))
        }
        ws.send(json.toString())
        return frameId
    }

    fun disconnect() {
        stopped = true
        reconnectHandler?.removeCallbacksAndMessages(null)
        webSocket?.close(1000, "done")
        webSocket = null
        isConnected = false
    }

    companion object {
        private const val TAG = "DetectorClient"
    }
}
