package com.mdmesh.kiosk

/**
 * Packages that must be lock-task allowlisted on every managed device even though the console cannot
 * offer them in its app picker (they have no launcher icon, so the picker - which lists launchable
 * apps only - never shows them) and staff cannot pin them.
 *
 * Why this matters: in lock-task (kiosk) mode Android only lets an allowlisted package start an
 * activity inside the locked task. When an allowed app (Chrome, WhatsApp, a catalogue app...) hands a
 * PDF or Office file to the system, the viewer that answers is a different package; if that package
 * is not allowlisted the open is silently blocked.
 *
 * Every entry here is a document viewer that ships on the fleet's Xiaomi/Redmi tablets:
 *  - `cn.wps.xiaomi.abroad.lite` - "Mi Doc Viewer (Powered by WPS)", preinstalled under /product, opens
 *    PDF/Word/Excel/PowerPoint, no launcher entry.
 *
 * Allowlisting a package that is not installed is harmless.
 */
object KioskAllowlist {
    val ALWAYS_ALLOWED: List<String> = listOf(
        "cn.wps.xiaomi.abroad.lite",
    )

    /** The full lock-task package set: what the console asked for + the agent itself + [ALWAYS_ALLOWED]. */
    fun effective(requested: List<String>, ownPackage: String): List<String> =
        (requested + ownPackage + ALWAYS_ALLOWED).filter { it.isNotBlank() }.distinct()
}
