package com.mdmesh.core.device

import android.content.Context
import com.mdmesh.proto.AppInfo

/**
 * Process-lifetime cache of [AppInventoryCollector.scan] — warmed once by
 * [com.mdmesh.agent.admin.DeviceOwnerInitializer] right after enrollment (including system apps,
 * matching the collector's own definition of "system": pre-installed but still launcher-visible,
 * not headless daemons), so the "Manage apps" screen never has to wait on a live scan the first
 * time an admin actually wants to add/remove apps from the kiosk allowlist — it's already there.
 *
 * Not persisted (installed-app set changes with app installs/removals, so a stale on-disk cache
 * would just be a second source of truth to keep in sync) - re-scanning is fast because
 * [AppInventoryCollector] already resolves everything in one batched PackageManager query, so a
 * process restart paying that cost once is a non-issue.
 */
object AppInventoryCache {
    @Volatile private var cached: List<AppInfo>? = null

    /** Populates (or refreshes) the cache. Safe to call from a background thread/coroutine;
     *  cheap enough (see [AppInventoryCollector]'s own doc comment) to not need debouncing. */
    fun warm(context: Context) {
        cached = runCatching { AppInventoryCollector(context).scan() }.getOrNull()
    }

    /** Cached apps if [warm] has run and succeeded at least once, else null - callers fall back
     *  to a live [AppInventoryCollector.scan] rather than showing nothing. */
    fun get(): List<AppInfo>? = cached
}
