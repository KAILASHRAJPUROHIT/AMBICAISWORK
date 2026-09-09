package com.mdmesh.core.telemetry

import android.app.KeyguardManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import com.mdmesh.policy.wifi.DpmHandle
import com.mdmesh.proto.SecurityPosture
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.time.LocalDate
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class SecurityCollector @Inject constructor(
    @ApplicationContext private val context: Context,
    private val handle: DpmHandle,
) {
    fun collect(): SecurityPosture {
        val km = context.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
        val adb = Settings.Global.getInt(context.contentResolver, Settings.Global.ADB_ENABLED, 0) == 1
        val dev = Settings.Global.getInt(context.contentResolver, Settings.Global.DEVELOPMENT_SETTINGS_ENABLED, 0) == 1
        val unknown = runCatching {
            @Suppress("DEPRECATION")
            Settings.Secure.getInt(context.contentResolver, Settings.Secure.INSTALL_NON_MARKET_APPS, 0) == 1
        }.getOrDefault(false)
        return SecurityPosture(
            storageEncrypted = isEncrypted(),
            deviceSecure = km.isDeviceSecure,
            adbEnabled = adb,
            devOptionsEnabled = dev,
            unknownSourcesAllowed = unknown,
            patchAgeDays = patchAgeDays(
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) Build.VERSION.SECURITY_PATCH else null,
                LocalDate.now().toEpochDay(),
            ),
            isDeviceOwner = handle.dpm.isDeviceOwnerApp(context.packageName),
            rootIndicators = detectRootIndicators(
                buildTags = Build.TAGS,
                installedPackages = installedPackageNames(),
                suPathExists = { path -> runCatching { File(path).exists() }.getOrDefault(false) },
            ),
        )
    }

    private fun installedPackageNames(): Set<String> = runCatching {
        @Suppress("DEPRECATION")
        context.packageManager.getInstalledPackages(PackageManager.GET_META_DATA)
            .mapNotNull { it.packageName }
            .toSet()
    }.getOrDefault(emptySet())

    @Suppress("DEPRECATION")
    private fun isEncrypted(): Boolean {
        val dpm = handle.dpm
        return dpm.storageEncryptionStatus != android.app.admin.DevicePolicyManager.ENCRYPTION_STATUS_UNSUPPORTED &&
            dpm.storageEncryptionStatus != android.app.admin.DevicePolicyManager.ENCRYPTION_STATUS_INACTIVE
    }

    companion object {
        /** Pure: days between a "yyyy-MM-dd" security patch string and now; null if absent/unparseable. */
        fun patchAgeDays(patch: String?, nowEpochDay: Long): Int? = runCatching {
            (nowEpochDay - LocalDate.parse(patch).toEpochDay()).toInt()
        }.getOrNull()

        /** Known root-manager / root-shell app packages. Not exhaustive — these are the
         *  common, actively-maintained ones; a determined attacker can rename or hide any
         *  of this, so treat non-empty [rootIndicators] as a signal to investigate, not a
         *  cryptographic guarantee (that's what Play Integrity attestation is for). */
        private val ROOT_PACKAGES = setOf(
            "com.topjohnwu.magisk",
            "com.noshufou.android.su",
            "com.koushikdutta.superuser",
            "eu.chainfire.supersu",
            "com.kingroot.kinguser",
            "com.kingo.root",
            "com.smedialink.oneclickroot",
            "me.weishu.kernelsu",
        )

        private val SU_PATHS = listOf(
            "/system/bin/su", "/system/xbin/su", "/sbin/su",
            "/system/su", "/system/bin/.ext/.su", "/data/local/xbin/su", "/data/local/bin/su",
        )

        /** Pure: evaluates the standard local root-detection heuristics against injected
         *  inputs, so this logic is unit-testable without an Android runtime. */
        fun detectRootIndicators(
            buildTags: String?,
            installedPackages: Set<String>,
            suPathExists: (String) -> Boolean,
        ): List<String> = buildList {
            if (buildTags?.contains("test-keys") == true) add("test-keys build")
            val rootApp = ROOT_PACKAGES.firstOrNull { it in installedPackages }
            if (rootApp != null) add("root-manager app: $rootApp")
            if (SU_PATHS.any(suPathExists)) add("su binary present")
        }
    }
}
