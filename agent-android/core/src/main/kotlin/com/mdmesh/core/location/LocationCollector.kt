package com.mdmesh.core.location

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.Bundle
import android.os.CancellationSignal
import android.os.Looper
import androidx.core.content.ContextCompat
import com.mdmesh.proto.LocationDto
import dagger.hilt.android.qualifiers.ApplicationContext
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Reads the device location for telemetry.
 *
 * - **Passive** (default): the OS's freshest last-known fix across providers. If that fix is older than [STALE_MS]
 *   a short network-provider fix (a few seconds, no GPS) is tried so a parked-but-moved device is not reported from
 *   hours ago.
 * - **Active**: a fresh fix every call, GPS first, then the network provider, then last-known.
 * - **Fresh** ([collectFresh], used by the Locate command): the longest budget, GPS then network.
 *
 * Works on every supported Android version (API 30+ uses `getCurrentLocation`, older versions a single-update
 * listener). Never throws; returns null without a location permission, with location services off, or when no fix is
 * available. The most recent fresh fix is also remembered in memory so the next telemetry report cannot fall back to
 * an older OS-cached one.
 */
@Singleton
class LocationCollector @Inject constructor(
    @ApplicationContext private val context: Context,
    private val modeStore: LocationModeStore,
) {
    @Volatile private var lastFresh: Location? = null

    /** @param forceActive ask the OS for a FRESH fix even when the fleet is in passive mode (used while a tablet is lost offline). */
    fun collect(forceActive: Boolean = false): LocationDto? {
        if (!hasPermission()) return null
        val lm = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager ?: return null
        val loc = when {
            forceActive || modeStore.isActive() -> freshFix(lm, GPS_BUDGET_MS, NETWORK_BUDGET_MS)
            else -> {
                val known = best(lm)
                if (known == null || age(known) > STALE_MS) {
                    freshFix(lm, 0L, QUICK_NETWORK_BUDGET_MS) ?: known
                } else {
                    known
                }
            }
        }
        return loc?.let(::toDto)
    }

    /** Take a quick network fix and remember it, so the next report is current. Used while the device is moving. */
    fun refresh() {
        if (!hasPermission()) return
        val lm = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager ?: return
        freshFix(lm, 0L, QUICK_NETWORK_BUDGET_MS)
    }

    /** Longest-budget fix for an explicit "Locate now": GPS up to [LOCATE_GPS_BUDGET_MS], then network. */
    fun collectFresh(): LocationDto? {
        if (!hasPermission()) return null
        val lm = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager ?: return null
        return freshFix(lm, LOCATE_GPS_BUDGET_MS, NETWORK_BUDGET_MS)?.let(::toDto)
    }

    private fun toDto(it: Location) = LocationDto(
        lat = it.latitude,
        lon = it.longitude,
        accuracyM = if (it.hasAccuracy()) it.accuracy else null,
        provider = it.provider,
        capturedAt = it.time,
    )

    private fun hasPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    private fun age(l: Location): Long = System.currentTimeMillis() - l.time

    /** Freshest of the OS last-known fixes and our own most recent fresh fix. */
    private fun best(lm: LocationManager): Location? =
        listOfNotNull(lastKnown(lm), lastFresh).maxByOrNull { it.time }

    /** Fresh fix: GPS for up to [gpsMs] (skipped when 0 or the provider is off), then network for up to [netMs]. */
    private fun freshFix(lm: LocationManager, gpsMs: Long, netMs: Long): Location? {
        val gps = if (gpsMs > 0 && enabled(lm, LocationManager.GPS_PROVIDER)) {
            singleFix(lm, LocationManager.GPS_PROVIDER, gpsMs)
        } else {
            null
        }
        val fix = gps ?: if (enabled(lm, LocationManager.NETWORK_PROVIDER)) {
            singleFix(lm, LocationManager.NETWORK_PROVIDER, netMs)
        } else {
            null
        }
        if (fix != null) lastFresh = fix
        return fix ?: best(lm)
    }

    private fun enabled(lm: LocationManager, provider: String): Boolean =
        runCatching { lm.isProviderEnabled(provider) }.getOrDefault(false)

    /** Freshest last-known location across all enabled providers (cheap, no active GPS). */
    @SuppressLint("MissingPermission") // gated by the callers' hasPermission() check
    private fun lastKnown(lm: LocationManager): Location? = runCatching {
        lm.allProviders
            .mapNotNull { p -> runCatching { lm.getLastKnownLocation(p) }.getOrNull() }
            .maxByOrNull { it.time }
    }.getOrNull()

    /** One fix from [provider] within [timeoutMs]; null on timeout or failure. Blocks the calling (background) thread. */
    @SuppressLint("MissingPermission") // gated by the callers' hasPermission() check
    private fun singleFix(lm: LocationManager, provider: String, timeoutMs: Long): Location? = runCatching {
        val latch = CountDownLatch(1)
        val ref = AtomicReference<Location?>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val cancel = CancellationSignal()
            lm.getCurrentLocation(provider, cancel, context.mainExecutor) { loc ->
                ref.set(loc); latch.countDown()
            }
            if (!latch.await(timeoutMs, TimeUnit.MILLISECONDS)) cancel.cancel()
        } else {
            val listener = object : LocationListener {
                override fun onLocationChanged(location: Location) { ref.set(location); latch.countDown() }
                @Deprecated("Deprecated in Java")
                override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) = Unit
                override fun onProviderEnabled(provider: String) = Unit
                override fun onProviderDisabled(provider: String) = Unit
            }
            @Suppress("DEPRECATION")
            lm.requestSingleUpdate(provider, listener, Looper.getMainLooper())
            if (!latch.await(timeoutMs, TimeUnit.MILLISECONDS)) lm.removeUpdates(listener)
        }
        ref.get()
    }.getOrNull()

    private companion object {
        /** A last-known fix older than this is not trusted as "current" in passive mode. */
        const val STALE_MS = 10 * 60_000L
        const val QUICK_NETWORK_BUDGET_MS = 6_000L
        const val NETWORK_BUDGET_MS = 8_000L
        const val GPS_BUDGET_MS = 20_000L
        const val LOCATE_GPS_BUDGET_MS = 30_000L
    }
}
