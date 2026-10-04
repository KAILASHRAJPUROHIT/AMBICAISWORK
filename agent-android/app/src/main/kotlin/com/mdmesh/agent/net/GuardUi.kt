package com.mdmesh.agent.net

/** What the connectivity guard wants on screen, shared with the two full-screen activities. */
object GuardUi {
    @Volatile var blockWanted = false
    @Volatile var lockdownWanted = false
    @Volatile var blockVisible = false
    @Volatile var lockdownVisible = false
    /** While an administrator is working in the lockdown panel (Wi-Fi settings, entering a code) the screen is not re-launched. */
    @Volatile var adminUntil = 0L
    @Volatile var online = false
    @Volatile var offlineSince: Long? = null
    @Volatile var attempts = 0
    @Volatile var openSeen = 0
}
