package com.mdmesh.core.power

import android.content.Context
import com.mdmesh.proto.DeviceAction
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Persists the connectivity power mode. Default [DeviceAction.POWER_ALWAYS_ON]: hold the wake
 * socket 24/7 so queued commands arrive immediately. [DeviceAction.POWER_ADAPTIVE] is an explicit
 * battery-saving opt-in: it holds the socket only while the screen is on or charging and otherwise
 * relies on the doze-proof heartbeat. Set remotely via the `device.powerMode` command.
 */
@Singleton
class PowerModeStore @Inject constructor(@ApplicationContext context: Context) {
    private val prefs = context.getSharedPreferences("mdm_power", Context.MODE_PRIVATE)

    fun get(): String = prefs.getString(KEY, DeviceAction.POWER_ALWAYS_ON) ?: DeviceAction.POWER_ALWAYS_ON

    fun set(mode: String) {
        val normalized = if (mode == DeviceAction.POWER_ALWAYS_ON) DeviceAction.POWER_ALWAYS_ON
                         else DeviceAction.POWER_ADAPTIVE
        prefs.edit().putString(KEY, normalized).apply()
    }

    fun isAlwaysOn(): Boolean = get() == DeviceAction.POWER_ALWAYS_ON

    private companion object { const val KEY = "mode" }
}
