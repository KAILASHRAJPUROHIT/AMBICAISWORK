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
 *  - `com.google.android.apps.docs` - Google Drive. On tablets with Google services it is the DEFAULT PDF viewer
 *    (`PdfViewerActivity`), so a PDF opened from any allowed app lands here, not in the Mi Doc Viewer. Tab 3's log
 *    showed "Attempted Lock Task Mode violation ... apps.docs/PdfViewerActivity" on every attempt until this was added.
 *    Only the viewer is reachable this way; the Drive app itself is not offered in the kiosk grid.
 *  - Google Docs / Sheets / Slides - the default handlers for Word, Excel and PowerPoint files on the same tablets.
 *
 * Allowlisting a package that is not installed is harmless.
 */
object KioskAllowlist {
    val ALWAYS_ALLOWED: List<String> = listOf(
        "cn.wps.xiaomi.abroad.lite",
        "com.google.android.apps.docs",
        "com.google.android.apps.docs.editors.docs",
        "com.google.android.apps.docs.editors.sheets",
        "com.google.android.apps.docs.editors.slides",
        // Hosts the screen-capture consent dialog for live remote view; blocked inside lock-task otherwise.
        "com.android.systemui",
        // Xiaomi's "allow this adb install?" confirmation (AdbInstallActivity) and the stock installers.
        // Blocked by lock-task, every `adb install` from the shop PC is cancelled with
        // INSTALL_FAILED_USER_RESTRICTED before anyone can approve it.
        "com.miui.securitycenter",
        "com.miui.packageinstaller",
        "com.android.packageinstaller",
        "com.google.android.packageinstaller",
    )

    /** The full lock-task package set: what the console asked for + the agent itself + [ALWAYS_ALLOWED]. */
    fun effective(requested: List<String>, ownPackage: String): List<String> =
        (requested + ownPackage + ALWAYS_ALLOWED).filter { it.isNotBlank() }.distinct()
}
