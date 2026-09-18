package com.mdmesh.core.remote

import com.mdmesh.proto.RemoteSessionStartPayload

/** App-layer bridge for remote capture. Command handlers live in :core and must not depend on
 * the :app foreground-service implementation. */
interface RemoteCaptureController {
    fun start(payload: RemoteSessionStartPayload): Boolean
    fun stop()
}
