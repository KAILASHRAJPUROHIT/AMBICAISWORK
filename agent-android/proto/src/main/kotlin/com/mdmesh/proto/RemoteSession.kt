package com.mdmesh.proto

import kotlinx.serialization.Serializable

/**
 * Payload of `device.remoteSessionStart` — begin periodic screen/camera/mic capture for a bounded
 * duration. Not continuous live video/audio: there is no Device-Owner-silent path to true live
 * streaming on stock Android (MediaProjection needs a fresh consent dialog every session; screen
 * capture without one needs the on-device accessibility-service toggle — see
 * [com.mdmesh.core.permission.ScreenCaptureAccessibilityPermission] — enabled once during setup),
 * so this is what's actually achievable: a still capture per [kinds] every [intervalSec], uploaded
 * as it's taken, until [durationSec] elapses or `device.remoteSessionStop` arrives.
 *
 * @property kinds which of `screen | cameraFront | cameraBack | mic` to capture this session.
 */
@Serializable
data class RemoteSessionStartPayload(
    val sessionId: String,
    val durationSec: Int = 300,
    val intervalSec: Int = 3,
    val kinds: List<String> = listOf("screen", "cameraFront", "cameraBack", "mic"),
)
