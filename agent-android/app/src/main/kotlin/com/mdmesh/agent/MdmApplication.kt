package com.mdmesh.agent

import android.app.Application
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject

/**
 * Hilt application root. Also supplies the Hilt-aware [HiltWorkerFactory] so
 * WorkManager can construct injected workers. Scheduling is deliberately owned by
 * the Device Owner lifecycle callbacks, never application startup: Android loads
 * the DPC while Setup Wizard is still completing provisioning.
 */
@HiltAndroidApp
class MdmApplication : Application(), Configuration.Provider {

    @Inject lateinit var workerFactory: HiltWorkerFactory

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setWorkerFactory(workerFactory)
            .build()

    override fun onCreate() {
        super.onCreate()
        installCrashGuard()
    }

    private fun installCrashGuard() {
        val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            runCatching {
                val trace = java.io.StringWriter().also { throwable.printStackTrace(java.io.PrintWriter(it)) }.toString()
                val file = java.io.File(filesDir, "last_crash.txt")
                file.writeText("${System.currentTimeMillis()}\n$trace")
                // Record as event so it's uploaded on next check-in
                com.mdmesh.core.telemetry.EventLog(this)
                    .record("crash", trace.take(3800))
            }
            // Delegate to system handler (kills process) — but we've saved the trace
            defaultHandler?.uncaughtException(thread, throwable)
        }
    }

}
