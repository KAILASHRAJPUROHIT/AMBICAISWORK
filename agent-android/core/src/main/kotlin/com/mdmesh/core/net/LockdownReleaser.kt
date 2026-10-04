package com.mdmesh.core.net

/** Lifts the offline lockdown. Implemented by the app's connectivity guard; used by the console command. */
interface LockdownReleaser {
    fun release(reason: String)
}
