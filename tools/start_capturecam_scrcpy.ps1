$ErrorActionPreference = 'Stop'

$adbPath = 'C:\platform-tools\adb.exe'
$scrcpyPath = 'C:\Users\kaila\Desktop\JewelleryCatalogTool\scrcpy\scrcpy-win64-v4.1\scrcpy.exe'

if (-not (Test-Path -LiteralPath $adbPath)) {
    throw "adb.exe not found at $adbPath"
}
if (-not (Test-Path -LiteralPath $scrcpyPath)) {
    throw "scrcpy.exe not found at $scrcpyPath"
}

# scrcpy interprets ADB as an executable path. The machine-level value points
# at C:\platform-tools (a directory), which produces CreateProcessW error 5.
$env:ADB = $adbPath

while ($true) {
    # Android Wireless Debugging rotates its TLS port. Never persist an old
    # endpoint; rediscover it before launch and after every device disconnect.
    $service = & $adbPath mdns services |
        Select-String '_adb-tls-connect._tcp' |
        Select-Object -First 1
    if (-not $service) {
        Write-Host 'CaptureCam tablet not found; retrying in 2 seconds...'
        Start-Sleep -Seconds 2
        continue
    }
    $tabletEndpoint = ($service.Line -split '\s+')[-1]
    if ($tabletEndpoint -notmatch '^\d{1,3}(\.\d{1,3}){3}:\d+$') {
        Write-Warning "Invalid ADB endpoint discovered: $tabletEndpoint"
        Start-Sleep -Seconds 2
        continue
    }

    & $adbPath connect $tabletEndpoint | Out-Host
    if ((& $adbPath -s $tabletEndpoint get-state 2>$null) -ne 'device') {
        Write-Host "Tablet ADB unavailable at $tabletEndpoint; rediscovering..."
        Start-Sleep -Seconds 1
        continue
    }

    & $scrcpyPath --serial $tabletEndpoint --window-title 'CaptureCam Tablet' --stay-awake
    $scrcpyExit = $LASTEXITCODE
    if ($scrcpyExit -eq 0) {
        # Normal window close is an intentional operator stop.
        break
    }
    Write-Host "scrcpy lost the tablet (exit $scrcpyExit); rediscovering..."
    Start-Sleep -Seconds 1
}
