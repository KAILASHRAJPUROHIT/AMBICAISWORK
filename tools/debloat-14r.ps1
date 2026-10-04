# Removes preinstalled China-HyperOS apps from the Redmi 14R for the CURRENT USER ONLY (pm uninstall -k --user 0).
# Nothing is deleted from the system partition and every removal is reversible with -Restore (or a factory reset).
#
#   .\debloat-14r.ps1 -Serial <adb serial>            # PREVIEW: lists what would be removed, changes nothing
#   .\debloat-14r.ps1 -Serial <adb serial> -Apply     # removes the listed apps that are installed on the phone
#   .\debloat-14r.ps1 -Serial <adb serial> -Restore   # brings them all back
#
# Run it after the factory reset and before provisioning (docs/14R-UPDATES.md, "Re-provisioning runbook").
# Only packages that are actually installed are touched, and anything on the keep-list is never removed.
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Serial,
    [switch] $Apply,
    [switch] $Restore
)

$ErrorActionPreference = 'Stop'

# Ads, analytics, feeds, shopping, games, bundled media and Xiaomi cloud/community apps. All are ordinary user apps.
$Remove = @(
    'com.miui.analytics',            # usage analytics
    'com.miui.systemAdSolution',     # system ads
    'com.miui.msa.global',           # ad service (global ROMs)
    'com.miui.hybrid',               # quick apps
    'com.miui.hybrid.accessory',
    'com.miui.player',               # music
    'com.miui.video',                # video
    'com.miui.fm',                   # radio
    'com.miui.newhome',              # content feed
    'com.mfashiongallery.emag',      # wallpaper carousel
    'com.miui.huanji',               # Mi Mover
    'com.miui.miservice',            # services and feedback
    'com.miui.bugreport',
    'com.miui.weather2',
    'com.miui.compass',
    'com.mi.health',
    'com.duokan.reader',             # Mi Reading
    'com.xiaomi.shop',               # Mi Store
    'com.xiaomi.vipaccount',         # Mi Community
    'com.xiaomi.gamecenter',
    'com.xiaomi.jr',                 # Mi Finance
    'com.miui.virtualsim',
    # Third-party China preloads that show on the home screen
    'cn.wps.moffice_eng', 'cn.wps.moffice_eng.xiaomi.lite',   # WPS Office
    'com.autonavi.minimap',          # AutoNavi / Amap
    'com.baidu.searchbox',           # Baidu
    'com.dragon.read', 'com.phoenix.read', 'com.xs.fm',        # Fanqie novels / audio
    'com.eg.android.AlipayGphone',   # Alipay
    'com.mipay.wallet',              # Mi Pay wallet
    'com.quark.browser',             # Quark browser
    'com.sankuai.meituan',           # Meituan
    'com.sina.weibo',                # Weibo
    'com.smile.gifmaker',            # Kuaishou
    'com.ss.android.article.news',   # Toutiao
    'com.ss.android.ugc.aweme',      # Douyin
    'com.taobao.idlefish', 'com.taobao.taobao',
    'com.xunmeng.pinduoduo',         # Pinduoduo
    'com.xunlei.downloadprovider',   # Xunlei
    'com.xiaomi.smarthome',          # Mi Home
    'com.xiaomi.tinygame',           # mini games
    'com.xiaomi.market',             # App Store
    'com.miui.themestore',           # Themes
    'com.miui.voiceassistProxy',     # Xiao AI voice assistant
    'com.miui.newmidrive',           # Mi Drive
    'com.miui.greenguard',           # Kids space
    'com.android.email'
)

# Never removed, even if someone adds them to the list above.
$Keep = @(
    'com.mdmesh.agent', 'com.mdmesh.agent.cn', 'com.ornate.nx', 'com.bis.bisapp',
    'com.android.systemui', 'com.android.settings', 'com.miui.home', 'com.miui.securitycenter',
    'com.miui.packageinstaller', 'com.android.packageinstaller', 'com.android.permissioncontroller',
    'com.android.phone', 'com.android.contacts', 'com.android.camera', 'com.android.chrome',
    'com.miui.gallery', 'com.miui.calculator', 'com.xiaomi.xmsf', 'com.xiaomi.account', 'com.android.providers.settings',
    'com.miui.securitymanager', 'com.android.providers.downloads.ui', 'com.android.deskclock', 'com.android.soundrecorder',
    'com.xiaomi.scanner', 'com.google.android.documentsui', 'com.android.fileexplorer', 'com.android.mms', 'com.android.browser',
    'com.miui.notes', 'com.miui.password', 'com.miui.screenrecorder', 'com.miui.mediaeditor', 'com.android.calendar',
    'com.baidu.input_mi', 'com.iflytek.inputmethod.miui', 'com.sohu.inputmethod.sogou.xiaomi', 'com.miui.cleanmaster'
)

function Invoke-Adb([string[]] $a) { & adb.exe -s $Serial @a 2>&1 }

if (-not ((& adb devices) -match "^$([regex]::Escape($Serial))\s+device$")) { throw "Device $Serial is not connected/authorized in adb." }
$model = (Invoke-Adb @('shell', 'getprop', 'ro.product.model')) -join ''
if ($model.Trim() -ne '2411DRN47C') { throw "Refusing: this is '$($model.Trim())', not the Redmi 14R (2411DRN47C)." }

$installed = (Invoke-Adb @('shell', 'pm', 'list', 'packages')) | ForEach-Object { ($_ -replace '^package:', '').Trim() }
$targets = $Remove | Where-Object { ($_ -notin $Keep) -and ($installed -contains $_) }
$absent = $Remove | Where-Object { $installed -notcontains $_ }

Write-Host "Redmi 14R $Serial"
Write-Host ("Installed and on the list: {0}   Not present on this phone: {1}" -f @($targets).Count, @($absent).Count)

if ($Restore) {
    foreach ($p in $Remove) {
        if ($p -in $Keep) { continue }
        $r = (Invoke-Adb @('shell', 'cmd', 'package', 'install-existing', $p)) -join ' '
        $e = (Invoke-Adb @('shell', 'pm', 'enable', '--user', '0', $p)) -join ' '
        Write-Host ("  restore {0,-34} {1} | {2}" -f $p, $r.Trim(), $e.Trim())
    }
    return
}

foreach ($p in $targets) {
    if ($Apply) {
        $r = (Invoke-Adb @('shell', 'pm', 'uninstall', '-k', '--user', '0', $p)) -join ' '
        if ($r -notmatch 'Success') {
            # Updated system apps cannot be uninstalled for good; disabling hides them and stops them running.
            $d = (Invoke-Adb @('shell', 'pm', 'disable-user', '--user', '0', $p)) -join ' '
            Write-Host ("  hidden  {0,-34} {1}" -f $p, $d.Trim())
        } else {
            Write-Host ("  removed {0,-34} {1}" -f $p, $r.Trim())
        }
    } else {
        Write-Host ("  would remove {0}" -f $p)
    }
}
if (-not $Apply) { Write-Host "`nPreview only. Re-run with -Apply to remove them (reversible with -Restore)." }
