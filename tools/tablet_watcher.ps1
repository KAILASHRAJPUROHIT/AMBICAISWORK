# Logon watcher for the CaptureCam tablet (Redmi Pad 2 Pro).
#  1. Keeps the tablet feed server (dashboard live screen) running.
#  2. Keeps wireless ADB connected across tablet/laptop reboots: reads the
#     ip:port CaptureCam reports (data\tablet_adb_endpoint.json), connects,
#     and pins classic tcpip :5555 so the connection survives TLS-port churn.
#  3. Opens the desktop scrcpy mirror once each time CaptureCam starts on the
#     tablet (standing rule: always give scrcpy when the app is open).
# Only ever runs `adb tcpip` when :5555 is NOT already up -- restarting adbd
# on a live link is what used to close scrcpy and rotate the TLS port.
$ErrorActionPreference = 'SilentlyContinue'
$Main    = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Adb     = 'C:\platform-tools\adb.exe'
$Launch  = Join-Path $PSScriptRoot 'start_capturecam_scrcpy.ps1'
$EndFile = Join-Path $Main 'data\tablet_adb_endpoint.json'
$CfgFile = Join-Path $Main 'config\tablet_feed.json'
$Log     = Join-Path $Main 'logs\tablet_watcher.log'
$Py      = 'C:\Users\kaila\AppData\Local\Programs\Python\Python312\pythonw.exe'
$env:ADB = $Adb
$script:scrcpyOpenedForRun = $false

function Log($m) { Add-Content -Path $Log -Value ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m) }
function Online($ep) { $s = & $Adb -s $ep get-state 2>$null; return ($s -eq 'device') }
function Try-Connect($ep) { & $Adb connect $ep 2>&1 | Out-Null; return (Online $ep) }

function Feed-Status {
    try { return Invoke-RestMethod -Uri 'http://127.0.0.1:7670/status' -TimeoutSec 6 } catch { return $null }
}

function Ensure-Feed {
    if (Feed-Status) { return }
    Log 'feed server down - starting'
    Start-Process -FilePath $Py -ArgumentList ('"{0}"' -f (Join-Path $Main 'tablet_feed_server.py')) `
        -WindowStyle Hidden -WorkingDirectory $Main
}

function Read-Endpoint {
    if (Test-Path $EndFile) { return (Get-Content $EndFile -Raw | ConvertFrom-Json) }
    return $null
}

function Candidate-Ips {
    $ips = @()
    $e = Read-Endpoint
    if ($e -and $e.ip) { $ips += $e.ip }
    if (Test-Path $CfgFile) { $c = Get-Content $CfgFile -Raw | ConvertFrom-Json; if ($c.serial -match '^([\d.]+):') { $ips += $Matches[1] } }
    return ($ips | Select-Object -Unique)
}

function Ensure-Adb {
    foreach ($ip in (Candidate-Ips)) {
        $stable = "${ip}:5555"
        if (Online $stable) { return $stable }
        if (Try-Connect $stable) { Log "connected $stable"; return $stable }
        # :5555 is down (tablet rebooted) -> use the reported TLS endpoint, then pin :5555.
        $tls = $null
        $e = Read-Endpoint
        if ($e -and $e.ip -eq $ip -and $e.port) { $tls = "${ip}:$($e.port)" }
        if (-not $tls) {
            $svc = & $Adb mdns services 2>$null | Select-String "_adb-tls-connect._tcp.*$([regex]::Escape($ip)):" | Select-Object -First 1
            if ($svc) { $tls = ($svc.Line -split '\s+')[-1] }
        }
        if ($tls -and (Try-Connect $tls)) {
            Log "connected via TLS $tls - pinning tcpip 5555"
            & $Adb -s $tls tcpip 5555 2>&1 | Out-Null
            Start-Sleep -Seconds 3
            if (Try-Connect $stable) { Log "stable endpoint up $stable"; return $stable }
            return $tls
        }
    }
    return $null
}

function Ensure-Scrcpy($serial) {
    $st = Feed-Status
    if (-not ($st -and $st.capturecam_running)) { $script:scrcpyOpenedForRun = $false; return }
    if ($script:scrcpyOpenedForRun) { return }   # operator may have closed it on purpose
    $script:scrcpyOpenedForRun = $true
    if (Get-Process -Name scrcpy -ErrorAction SilentlyContinue) { return }
    Log "CaptureCam started on tablet - opening scrcpy ($serial)"
    Start-Process powershell.exe -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',$Launch,'-Serial',$serial -WindowStyle Hidden
}

Log 'tablet watcher started'
& $Adb start-server 2>&1 | Out-Null
while ($true) {
    Ensure-Feed
    $serial = Ensure-Adb
    if ($serial) { Ensure-Scrcpy $serial }
    Start-Sleep -Seconds 10
}
