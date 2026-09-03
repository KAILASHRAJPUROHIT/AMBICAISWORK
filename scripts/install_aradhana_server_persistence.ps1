<#
Installs two machine-level Scheduled Tasks for the Billing-PC server:
one at Windows startup and a five-minute watchdog.  Both run as LocalSystem
so they are independent of any employee sign-in.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Control = Join-Path $Root "scripts\aradhana_service_control.ps1"
if (-not (Test-Path -LiteralPath $Control)) { throw "Missing service control script: $Control" }

$TaskCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Control`" start-prod"

function Register-AradhanaTask([string[]]$Arguments) {
    & schtasks.exe @Arguments | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Scheduled-task registration failed: $($Arguments -join ' ')" }
}

Register-AradhanaTask @("/Create", "/TN", "AradhanaAuditorServer", "/TR", $TaskCommand, "/SC", "ONSTART", "/RU", "SYSTEM", "/RL", "HIGHEST", "/F")
Register-AradhanaTask @("/Create", "/TN", "AradhanaAuditorServerWatchdog", "/TR", $TaskCommand, "/SC", "MINUTE", "/MO", "5", "/RU", "SYSTEM", "/RL", "HIGHEST", "/F")

Write-Host "Installed AradhanaAuditorServer (boot) and AradhanaAuditorServerWatchdog (every 5 minutes)."
