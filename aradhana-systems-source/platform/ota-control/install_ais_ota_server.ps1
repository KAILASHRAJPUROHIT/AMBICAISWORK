[CmdletBinding()]
param(
    [string]$PythonPath,
    [string]$BindAddress = '192.168.0.12',
    [int]$Port = 8091,
    [string]$RemoteSubnet = '192.168.0.0/24'
)

$ErrorActionPreference = 'Stop'
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'AIS OTA server installation requires an elevated PowerShell session.'
}
$root = $PSScriptRoot
$runner = Join-Path $root 'run_ota_server.ps1'
if (-not $PythonPath) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        'C:\Users\kaila\AppData\Local\Programs\Python\Python311\python.exe'
    ) | Select-Object -Unique
    $PythonPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not (Test-Path -LiteralPath $PythonPath)) { throw "Python not found: $PythonPath" }
& $PythonPath -c "import fastapi,uvicorn,cryptography" 2>$null
if ($LASTEXITCODE -ne 0) { throw "Required OTA Python modules missing in: $PythonPath" }

$taskName = 'AISOTAServer'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" -PythonPath `"$PythonPath`" -BindAddress `"$BindAddress`" -Port $Port" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 365)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'AIS signed LAN OTA release server' -Force | Out-Null

$ruleName = 'AIS OTA LAN only (TCP 8091)'
Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -LocalAddress $BindAddress -RemoteAddress $RemoteSubnet -Profile Private -Description 'AIS signed OTA server; private Aradhana LAN only.' | Out-Null

Start-ScheduledTask -TaskName $taskName
$deadline = (Get-Date).AddSeconds(20)
do {
    Start-Sleep -Milliseconds 750
    try {
        $health = Invoke-RestMethod "http://$BindAddress`:$Port/health" -TimeoutSec 2
        if ($health.status -eq 'healthy' -and $health.public_certificate) {
            Write-Host "AIS OTA server installed and verified at http://$BindAddress`:$Port" -ForegroundColor Green
            exit 0
        }
    } catch { }
} while ((Get-Date) -lt $deadline)
$taskInfo = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
throw "AIS OTA server did not become healthy. LastTaskResult=$($taskInfo.LastTaskResult). Check $env:ProgramData\AradhanaSystems\logs\ais-ota\ota-server.log"
