package com.mdmesh.core.telemetry

import android.app.usage.NetworkStatsManager
import android.content.Context
import android.net.ConnectivityManager
import com.mdmesh.proto.DataUsageDto
import dagger.hilt.android.qualifiers.ApplicationContext
import java.time.LocalDate
import java.time.ZoneId
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Reads today's cumulative cellular/Wi-Fi data usage for telemetry, via
 * [NetworkStatsManager.querySummaryForDevice]. Like [DynamicStateCollector.foregroundApp],
 * this needs the `PACKAGE_USAGE_STATS` special access grant — it is **not** silently
 * grantable via Device Owner, so this degrades to `null` (no data, not a crash) exactly the
 * same way until an admin enables Usage Access on-device. Window is local-midnight-to-now,
 * so each check-in reports a fresh running total for the current day rather than an
 * ever-growing since-boot counter.
 */
@Singleton
class NetworkUsageCollector @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    fun collect(): DataUsageDto? = runCatching {
        val nsm = context.getSystemService(Context.NETWORK_STATS_SERVICE)
            as? NetworkStatsManager ?: return null
        val (start, end) = todayWindowMillis()

        val mobile = summarize(nsm, ConnectivityManager.TYPE_MOBILE, start, end)
        val wifi = summarize(nsm, ConnectivityManager.TYPE_WIFI, start, end)
        if (mobile == null && wifi == null) return null

        DataUsageDto(
            mobileRxBytes = mobile?.first ?: 0L,
            mobileTxBytes = mobile?.second ?: 0L,
            wifiRxBytes = wifi?.first ?: 0L,
            wifiTxBytes = wifi?.second ?: 0L,
            windowStart = start,
        )
    }.getOrNull()

    /** Device-wide (all UIDs) rx/tx total for one network type; null if the query itself
     *  fails (e.g. no usage-access grant — caught by the outer runCatching too, this inner
     *  one isolates a failure on one network type from blanking out the other).
     *  [NetworkStatsManager.querySummaryForDevice] already returns one aggregated
     *  [NetworkStats.Bucket] for the whole device — unlike the per-UID [querySummary]
     *  cursor, there is nothing to iterate here. */
    private fun summarize(
        nsm: NetworkStatsManager,
        networkType: Int,
        start: Long,
        end: Long,
    ): Pair<Long, Long>? = runCatching {
        val bucket = nsm.querySummaryForDevice(networkType, null, start, end)
        bucket.rxBytes to bucket.txBytes
    }.getOrNull()

    private fun todayWindowMillis(): Pair<Long, Long> {
        val zone = ZoneId.systemDefault()
        val startOfDay = LocalDate.now(zone).atStartOfDay(zone).toInstant().toEpochMilli()
        return startOfDay to System.currentTimeMillis()
    }
}
