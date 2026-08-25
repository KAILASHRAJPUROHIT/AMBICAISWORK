$ErrorActionPreference = 'Stop'

$adbPath = 'C:\platform-tools\adb.exe'
$scrcpyPath = 'C:\Users\kaila\Desktop\JewelleryCatalogTool\scrcpy\scrcpy-win64-v4.1\scrcpy.exe'

if (-not (Test-Path -LiteralPath $adbPath)) {
    throw "adb.exe not found at $adbPath"
}
if (-not (Test-Path -LiteralPath $scrcpyPath)) {
    throw "scrcpy.exe not found at $scrcpyPath"
}

# Android Wireless Debugging rotates its TLS port. Never persist yesterday's
# endpoint; discover the tablet's current _adb-tls-connect service every run.
$service = & $adbPath mdns services |
    Select-String '_adb-tls-connect._tcp' |
    Select-Object -First 1
if (-not $service) {
    throw 'CaptureCam tablet not found. Enable Wireless debugging on the tablet.'
}
$tabletEndpoint = ($service.Line -split '\s+')[-1]
if ($tabletEndpoint -notmatch '^\d{1,3}(\.\d{1,3}){3}:\d+$') {
    throw "Invalid ADB endpoint discovered: $tabletEndpoint"
}

& $adbPath connect $tabletEndpoint | Out-Host
if ((& $adbPath -s $tabletEndpoint get-state 2>$null) -ne 'device') {
    throw "Tablet ADB connection failed: $tabletEndpoint"
}

# scrcpy interprets ADB as an executable path. The machine-level value points
# at C:\platform-tools (a directory), which produces CreateProcessW error 5.
$env:ADB = $adbPath
& $scrcpyPath --serial $tabletEndpoint --window-title 'CaptureCam Tablet' --stay-awake
