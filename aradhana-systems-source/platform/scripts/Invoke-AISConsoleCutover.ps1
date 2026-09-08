[CmdletBinding()]
param(
    [switch]$Commit
)

$ErrorActionPreference = 'Stop'
$platformRoot = 'C:\AradhanaSystems\platform'
$legacyRoot = 'C:\DEEPSEEK HARNESS'
$consoleRoot = Join-Path $platformRoot 'ais-owner-console'
$controlRoot = Join-Path $platformRoot 'ais-local-control-plane'
$runtimeRoot = 'C:\AradhanaSystems\runtime\ais-owner-console'
$nodePath = 'C:\Program Files\nodejs\node.exe'
$npmPath = 'C:\Program Files\nodejs\npm.cmd'
$pythonPath = 'C:\Users\kaila\AppData\Local\Programs\Python\Python311\python.exe'

function Get-ListenerProcessId {
    param([int]$Port)
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

function Wait-HttpHealthy {
    param([string]$Url, [int]$TimeoutSeconds = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) { return }
        } catch {}
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Service did not become healthy: $Url"
}

foreach ($path in @($consoleRoot, $controlRoot, $nodePath, $npmPath, $pythonPath)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required path missing: $path" }
}

Push-Location $consoleRoot
try {
    & $npmPath run build | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Central owner-console build failed.' }
} finally { Pop-Location }
Push-Location $controlRoot
try {
    & $npmPath run check | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Central control-plane validation failed.' }
} finally { Pop-Location }

$current = [pscustomobject]@{
    DashboardPort3000 = Get-ListenerProcessId 3000
    ControlPort4317 = Get-ListenerProcessId 4317
    ScannerPort8787 = Get-ListenerProcessId 8787
    PaymentPort8000 = Get-ListenerProcessId 8000
    OtaPort8091 = Get-ListenerProcessId 8091
}

if (-not $Commit) {
    [pscustomobject]@{
        Status = 'staged'
        Action = 'Run again with -Commit to switch only owner-console, local control-plane and project scanner to C:\AradhanaSystems.'
        Current = $current
        Untouched = 'payment-api, payment-web, AIS OTA, print router, QR server and all printers'
    } | Format-List
    exit 0
}

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logDir = Join-Path $runtimeRoot 'logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

# Stop only listeners belonging to the owner-console stack. No printer or business-service process is targeted.
foreach ($port in @(3000, 4317, 8787)) {
    $processId = Get-ListenerProcessId $port
    if ($processId) {
        Stop-Process -Id $processId -Force
        Start-Sleep -Milliseconds 300
    }
}

# With the legacy control-plane stopped, its SQLite database is a consistent final snapshot.
$legacyData = Join-Path $legacyRoot 'control-plane\data'
$centralData = Join-Path $controlRoot 'data'
$legacyDb = Join-Path $legacyData 'ais.db'
if (-not (Test-Path -LiteralPath $legacyDb)) { throw "Legacy control-plane database missing: $legacyDb" }
New-Item -ItemType Directory -Path $centralData -Force | Out-Null
Get-ChildItem -LiteralPath $centralData -Filter 'ais.db*' -File -ErrorAction SilentlyContinue | ForEach-Object {
    Move-Item -LiteralPath $_.FullName -Destination ($_.FullName + ".pre-cutover-$stamp") -Force
}
Copy-Item -LiteralPath $legacyDb -Destination (Join-Path $centralData 'ais.db') -Force

# Preserve D1 local state now that the legacy dashboard is stopped.
foreach ($stateFolder in @('.wrangler', '.local')) {
    $source = Join-Path (Join-Path $legacyRoot 'dashboard') $stateFolder
    $destination = Join-Path $consoleRoot $stateFolder
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
    }
}

Start-Process -FilePath $nodePath -ArgumentList @('--env-file-if-exists=.env', 'src/server.mjs') -WorkingDirectory $controlRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "control-plane-$stamp.out.log") -RedirectStandardError (Join-Path $logDir "control-plane-$stamp.err.log") | Out-Null
Start-Process -FilePath $npmPath -ArgumentList @('run', 'scan') -WorkingDirectory $consoleRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "scanner-$stamp.out.log") -RedirectStandardError (Join-Path $logDir "scanner-$stamp.err.log") | Out-Null
Start-Process -FilePath $npmPath -ArgumentList @('run', 'dev') -WorkingDirectory $consoleRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "owner-console-$stamp.out.log") -RedirectStandardError (Join-Path $logDir "owner-console-$stamp.err.log") | Out-Null

Wait-HttpHealthy 'http://127.0.0.1:4317/health'
Wait-HttpHealthy 'http://127.0.0.1:8787/health'
Wait-HttpHealthy 'http://localhost:3000/'

[pscustomobject]@{
    Status = 'cutover_complete'
    Dashboard = 'http://localhost:3000'
    ControlPlane = 'http://127.0.0.1:4317/health'
    Scanner = 'http://127.0.0.1:8787/health'
    DataSnapshot = (Join-Path $centralData 'ais.db')
    Logs = $logDir
    Untouched = 'payment-api, payment-web, AIS OTA, print router, QR server and all printers'
} | Format-List
