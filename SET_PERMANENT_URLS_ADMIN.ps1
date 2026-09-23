#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
$toolRoot = $PSScriptRoot
$cataloguePort = 7654
$capturePort = 7660

Set-Service -Name "AradhanaCatalogueTool" -StartupType Automatic
Set-Service -Name "AradhanaCaptureServer" -StartupType Automatic

foreach ($rule in @(
    @{ Name = "Aradhana Catalogue Tool 7654"; Port = $cataloguePort },
    @{ Name = "Aradhana Capture Server 7660"; Port = $capturePort }
)) {
    if (-not (Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule `
            -DisplayName $rule.Name `
            -Direction Inbound `
            -Action Allow `
            -Protocol TCP `
            -LocalPort $rule.Port `
            -Profile Private | Out-Null
    }
}

Restart-Service -Name "AradhanaCatalogueTool" -Force
Restart-Service -Name "AradhanaCaptureServer" -Force

$deadline = (Get-Date).AddSeconds(30)
$catalogueReady = $false
$captureReady = $false
while ((Get-Date) -lt $deadline -and (-not $catalogueReady -or -not $captureReady)) {
    try {
        $catalogue = Invoke-WebRequest `
            -Uri "http://127.0.0.1:$cataloguePort/api/health" `
            -UseBasicParsing `
            -TimeoutSec 2
        $catalogueReady = $catalogue.StatusCode -eq 200
    } catch {}
    try {
        & curl.exe --noproxy "*" -k -f -sS `
            --max-time 2 `
            "https://127.0.0.1:$capturePort/api/health" | Out-Null
        $captureReady = $LASTEXITCODE -eq 0
    } catch {}
    if (-not $catalogueReady -or -not $captureReady) {
        Start-Sleep -Milliseconds 500
    }
}

if (-not $catalogueReady) {
    throw "Catalogue service did not become ready on fixed port $cataloguePort"
}
if (-not $captureReady) {
    throw "Capture service did not become ready on fixed port $capturePort"
}

$network = Get-NetIPConfiguration | Where-Object {
    $_.IPv4DefaultGateway -and
    $_.IPv4Address.IPAddress -notlike "169.254.*"
} | Select-Object -First 1
$lanIp = $network.IPv4Address.IPAddress
$hostname = $env:COMPUTERNAME.ToLowerInvariant()

$report = @"
PERMANENT SERVICES ENABLED

Catalogue Studio:
http://${hostname}:$cataloguePort

Capture Server:
https://${hostname}.local:$capturePort/capture

Current fixed-IP fallbacks:
http://${lanIp}:$cataloguePort
https://${lanIp}:$capturePort/capture

Catalogue service: automatic, fixed port $cataloguePort
Capture service: automatic, fixed port $capturePort

Router requirement: reserve ${lanIp} for computer $env:COMPUTERNAME in DHCP.
"@
$report | Set-Content -LiteralPath (Join-Path $toolRoot "docs\PERMANENT_URLS.txt") -Encoding utf8
Write-Host $report -ForegroundColor Green
Write-Host "Setup complete. Press Enter to close." -ForegroundColor Cyan
Read-Host
