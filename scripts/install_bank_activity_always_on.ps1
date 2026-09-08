[CmdletBinding()]
param(
    # Use the default on the Billing PC. On a second LAN PC, pass the Billing-PC URL.
    [string]$ServerUrl = "http://127.0.0.1:8000/api/bank-activity"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$control = Join-Path $root "scripts\aradhana_service_control.ps1"
$notifier = Join-Path $root "scripts\start_bank_activity_notifier.ps1"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Administrator rights are required. Run install_bank_activity_always_on.cmd."
}
if (-not (Test-Path $control) -or -not (Test-Path $notifier)) { throw "Aradhana Auditor installation files are incomplete." }

# Backend/frontend: boots before a user logs in and restarts after a service crash.
$serviceAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$control`" -Mode start-prod"
$serviceTrigger = New-ScheduledTaskTrigger -AtStartup
$serviceSettings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 0)
$servicePrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName "AradhanaAuditorAlwaysOn" -Action $serviceAction -Trigger $serviceTrigger -Settings $serviceSettings -Principal $servicePrincipal -Description "Starts the Aradhana Auditor payment service at Windows boot." -Force | Out-Null

# Windows isolates services from the visible desktop. This task starts the
# topmost notification windows instantly whenever an interactive user logs in.
$notifierAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$notifier`" -ServerUrl `"$ServerUrl`""
$notifierTrigger = New-ScheduledTaskTrigger -AtLogOn
$notifierSettings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 0)
$interactiveUser = "$env:USERDOMAIN\$env:USERNAME"
$notifierPrincipal = New-ScheduledTaskPrincipal -UserId $interactiveUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "AradhanaBankActivityNotifier" -Action $notifierAction -Trigger $notifierTrigger -Settings $notifierSettings -Principal $notifierPrincipal -Description "Shows topmost Aradhana bank-transaction notifications after logon." -Force | Out-Null

# Keep LAN access constrained to private Windows networks.
foreach ($port in 5173, 8000) {
    $name = "Aradhana Auditor LAN $port"
    if (-not (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port -Profile Private | Out-Null
    }
}

& $control -Mode start-prod
& $notifier -ServerUrl $ServerUrl
& $notifier -ServerUrl $ServerUrl -Configure

Write-Host "Installed successfully."
Write-Host "Backend service: starts at Windows boot, including before logon."
Write-Host "Desktop notifier: starts at every user logon (Windows cannot show a popup while no desktop session exists)."
