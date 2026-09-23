param(
    # Android Wireless Debugging rotates this port. Pass the currently shown
    # endpoint when starting CaptureCam; the launcher converts it to stable
    # TCP ADB :5555 before opening scrcpy.
    [string]$Serial = ''
)

$ErrorActionPreference = 'Stop'

$adbPath = 'C:\platform-tools\adb.exe'
$scrcpyPath = 'C:\AradhanaSystems\projects\catalogue-capture\main\scrcpy\scrcpy-win64-v4.1\scrcpy.exe'
function Resolve-TabletEndpoint {
    param([string]$RequestedSerial)
    if ($RequestedSerial -match '^\d{1,3}(\.\d{1,3}){3}:\d+$') {
        return $RequestedSerial
    }
    $networkDevice = & $adbPath devices |
        Select-String '^\d{1,3}(\.\d{1,3}){3}:\d+\s+device$' |
        Select-Object -First 1
    if (-not $networkDevice) {
        throw 'No wireless Android device is connected. Pass -Serial IP:PORT.'
    }
    return ($networkDevice.Line -split '\s+')[0]
}

$bootstrapEndpoint = Resolve-TabletEndpoint $Serial
$tabletIp = ($bootstrapEndpoint -split ':')[0]
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
    # Prefer the operator-supplied live TLS endpoint. mDNS is fallback only;
    # it may list another tablet or emulator first.
    $tlsEndpoint = $bootstrapEndpoint
    if (-not (Test-AdbEndpoint $tlsEndpoint)) {
        $service = & $adbPath mdns services |
            Select-String "_adb-tls-connect._tcp.*$([regex]::Escape($tabletIp)):" |
            Select-Object -First 1
        if (-not $service) { return $false }
        $tlsEndpoint = ($service.Line -split '\s+')[-1]
        if ($tlsEndpoint -notmatch '^\d{1,3}(\.\d{1,3}){3}:\d+$' -or -not (Test-AdbEndpoint $tlsEndpoint)) { return $false }
    }
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
