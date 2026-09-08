[CmdletBinding()]
param(
    [string]$ServerUrl = "http://127.0.0.1:8000/api/bank-activity",
    [switch]$Elevated
)

$ErrorActionPreference = "Stop"

# Self-elevate once. Double-click this one file; no companion CMD launcher is needed.
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $args = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Elevated -ServerUrl `"$ServerUrl`""
    Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList $args
    exit $LASTEXITCODE
}

$root = $PSScriptRoot
$control = Join-Path $root "scripts\aradhana_service_control.ps1"
$notifier = Join-Path $root "scripts\start_bank_activity_notifier.ps1"
if (-not (Test-Path $control) -or -not (Test-Path $notifier)) {
    throw "Put this launcher in the Aradhana Payment Auditor project root, beside the scripts folder."
}

$serviceAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$control`" -Mode start-prod"
$serviceTrigger = New-ScheduledTaskTrigger -AtStartup
$serviceSettings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 0)
$servicePrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName "AradhanaAuditorAlwaysOn" -Action $serviceAction -Trigger $serviceTrigger -Settings $serviceSettings -Principal $servicePrincipal -Description "Starts Aradhana Auditor at Windows boot." -Force | Out-Null

$notifierAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$notifier`" -ServerUrl `"$ServerUrl`""
$notifierTrigger = New-ScheduledTaskTrigger -AtLogOn
$notifierSettings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 0)
$interactiveUser = "$env:USERDOMAIN\$env:USERNAME"
$notifierPrincipal = New-ScheduledTaskPrincipal -UserId $interactiveUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "AradhanaBankActivityNotifier" -Action $notifierAction -Trigger $notifierTrigger -Settings $notifierSettings -Principal $notifierPrincipal -Description "Shows Aradhana bank notifications after user logon." -Force | Out-Null

foreach ($port in 5173, 8000) {
    $rule = "Aradhana Auditor LAN $port"
    if (-not (Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $rule -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port -Profile Private | Out-Null
    }
}

& $control -Mode start-prod
& $notifier -ServerUrl $ServerUrl
& $notifier -ServerUrl $ServerUrl -Configure
Write-Host "Aradhana Bank Activity always-on setup complete."
