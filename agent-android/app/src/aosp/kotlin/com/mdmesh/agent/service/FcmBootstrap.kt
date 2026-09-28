package com.mdmesh.agent.service

import android.content.Context

/** aosp flavor has no Firebase; kept so MdmApplication compiles identically in both flavors. */
object FcmBootstrap {
    @Suppress("UNUSED_PARAMETER")
    fun start(context: Context) = Unit
}
