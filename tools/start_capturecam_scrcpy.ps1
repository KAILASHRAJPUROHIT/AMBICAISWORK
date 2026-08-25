$ErrorActionPreference = 'Stop'

$adbPath = 'C:\platform-tools\adb.exe'
$scrcpyPath = 'C:\Users\kaila\Desktop\JewelleryCatalogTool\scrcpy\scrcpy-win64-v4.1\scrcpy.exe'
$tabletIp = '192.168.0.22'
$stableEndpoint = "${tabletIp}:5555"

if (-not (Test-Path -LiteralPath $adbPath)) {
    throw "adb.exe not found at $adbPath"
}
if (-not (Test-Path -LiteralPath $scrcpyPath)) {
    throw "scrcpy.exe not found at $scrcpyPath"
}

# scrcpy interprets ADB as an executable path. The machine-level value points
# at C:\platform-tools (a directory), which produces CreateProcessW error 5.
$env:ADB = $adbPath

function Test-AdbEndpoint([string]$Endpoint) {
    try {
        $oldPreference = $ErrorActionPreference
        $ErrorActionPreference = 'SilentlyContinue'
        & $adbPath connect $Endpoint 2>$null | Out-Null
        $state = & $adbPath -s $Endpoint get-state 2>$null
        return ($state -eq 'device')
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $oldPreference
    }
}

function Enable-StableAdbEndpoint {
    # Android's Wireless Debugging TLS endpoint changes whenever adbd is
    # restarted. Use it only to bootstrap classic authenticated TCP ADB on a
    # fixed port. Scrcpy then survives TLS/mDNS port rotation.
    $service = & $adbPath mdns services |
        Select-String '_adb-tls-connect._tcp' |
        Select-Object -First 1
    if (-not $service) { return $false }
    $tlsEndpoint = ($service.Line -split '\s+')[-1]
    if ($tlsEndpoint -notmatch '^\d{1,3}(\.\d{1,3}){3}:\d+$') { return $false }
    if (-not (Test-AdbEndpoint $tlsEndpoint)) { return $false }
    & $adbPath -s $tlsEndpoint tcpip 5555 | Out-Host
    Start-Sleep -Seconds 2
    return (Test-AdbEndpoint $stableEndpoint)
}

# Never create competing mirror/ADB-video sessions. They waste the same 5 GHz
# link used for Sony originals and look like repeated close/reopen windows.
$existingScrcpy = Get-Process -Name scrcpy -ErrorAction SilentlyContinue
if ($existingScrcpy) {
    Write-Host 'CaptureCam Tablet mirror is already running. Close it before starting another.'
    exit 0
}

while ($true) {
    if (-not (Test-AdbEndpoint $stableEndpoint) -and -not (Enable-StableAdbEndpoint)) {
        Write-Host 'CaptureCam tablet unavailable; retrying stable ADB in 2 seconds...'
        Start-Sleep -Seconds 2
        continue
    }

    & $scrcpyPath --serial $stableEndpoint --window-title 'CaptureCam Tablet' `
        --stay-awake --no-audio --max-fps=30 --max-size=1280 --video-bit-rate=6M
    $scrcpyExit = $LASTEXITCODE
    if ($scrcpyExit -eq 0) {
        # Normal window close is an intentional operator stop.
        break
    }
    Write-Host "scrcpy lost the tablet (exit $scrcpyExit); recovering stable ADB..."
    Start-Sleep -Seconds 1
}
