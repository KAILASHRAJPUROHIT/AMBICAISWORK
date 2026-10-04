package com.mdmesh.agent.service

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionConfig
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import androidx.core.content.ContextCompat
import com.mdmesh.core.remote.ScreenCaptureAccessibilityService
import com.mdmesh.proto.RemoteSessionStartPayload

/**
 * Invisible hop that asks Android for screen-capture consent for a live session. The Accessibility
 * service presses the system dialog's button (see [ScreenCaptureAccessibilityService.armProjectionConsent]),
 * so nobody has to be at the tablet. If consent does not arrive in time, the session falls back to
 * periodic screenshots so the admin still gets a picture.
 */
class ProjectionConsentActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private var finished = false
    private lateinit var session: RemoteSessionStartPayload
    private var autoConsent = true

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        session = RemoteSessionStartPayload(
            sessionId = intent.getStringExtra(EXTRA_SESSION_ID) ?: "",
            durationSec = intent.getIntExtra(EXTRA_DURATION, 300),
            intervalSec = intent.getIntExtra(EXTRA_INTERVAL, 3),
            kinds = listOf("screen"),
        )
        autoConsent = intent.getBooleanExtra(EXTRA_AUTO, true)
        if (savedInstanceState != null) return
        runCatching {
            // autoConsent=false: leave the system prompt for a person at the tablet to accept.
            if (autoConsent) ScreenCaptureAccessibilityService.armProjectionConsent()
            val mpm = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            val captureIntent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                mpm.createScreenCaptureIntent(MediaProjectionConfig.createConfigForDefaultDisplay())
            } else {
                mpm.createScreenCaptureIntent()
            }
            @Suppress("DEPRECATION")
            startActivityForResult(captureIntent, REQ)
        }.onFailure {
            Log.e(TAG, "could not request screen capture", it)
            fallbackAndFinish()
        }
        handler.postDelayed({ fallbackAndFinish() }, if (autoConsent) 45_000L else 120_000L)
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQ || finished) return
        ScreenCaptureAccessibilityService.disarmProjectionConsent()
        if (resultCode == RESULT_OK && data != null) {
            finished = true
            handler.removeCallbacksAndMessages(null)
            ContextCompat.startForegroundService(this, LiveScreenService.intent(this, resultCode, data, session.durationSec))
            finish()
        } else {
            fallbackAndFinish()
        }
    }

    private fun fallbackAndFinish() {
        if (finished) return
        finished = true
        handler.removeCallbacksAndMessages(null)
        ScreenCaptureAccessibilityService.disarmProjectionConsent()
        Log.w(TAG, "live consent not granted - falling back to snapshots")
        runCatching { ContextCompat.startForegroundService(this, RemoteCaptureService.intent(this, session)) }
        finish()
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    companion object {
        private const val TAG = "ProjectionConsent"
        private const val REQ = 4711
        private const val EXTRA_SESSION_ID = "sessionId"
        private const val EXTRA_DURATION = "durationSec"
        private const val EXTRA_INTERVAL = "intervalSec"
        private const val EXTRA_AUTO = "autoConsent"

        fun intent(context: Context, payload: RemoteSessionStartPayload): Intent =
            Intent(context, ProjectionConsentActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_NO_ANIMATION)
                .putExtra(EXTRA_SESSION_ID, payload.sessionId)
                .putExtra(EXTRA_DURATION, payload.durationSec)
                .putExtra(EXTRA_INTERVAL, payload.intervalSec)
                .putExtra(EXTRA_AUTO, payload.autoConsent)
    }
}
