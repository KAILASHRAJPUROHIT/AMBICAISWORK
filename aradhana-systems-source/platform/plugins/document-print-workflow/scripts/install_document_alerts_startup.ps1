[CmdletBinding()]
param(
    [string]$PythonPath = (Get-Command python -ErrorAction Stop).Source,
    [string]$ScannerApi = 'https://print.aradhanajewellers.com'
)

$ErrorActionPreference = 'Stop'
$pluginRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $PSScriptRoot 'Start-DocumentAlerts.ps1'
if (-not (Test-Path -LiteralPath $launcher)) { throw "Document alert launcher missing: $launcher" }
if (-not (Test-Path -LiteralPath $PythonPath)) { throw "Python not found: $PythonPath" }

# UI notifications must run as the signed-in biller. This task deliberately
# does not use SYSTEM; SYSTEM cannot safely show a biller-facing window.
$taskName = 'AISDocumentAlerts'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$launcher`" -PythonPath `"$PythonPath`" -ScannerApi `"$ScannerApi`"" -WorkingDirectory $pluginRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel LeastPrivilege
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 365) -StartWhenAvailable
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'AIS top-right QR document alerts for the signed-in biller' -Force | Out-Null
Write-Host "Installed $taskName for $env:USERNAME. It starts when this user signs in." -ForegroundColor Green
