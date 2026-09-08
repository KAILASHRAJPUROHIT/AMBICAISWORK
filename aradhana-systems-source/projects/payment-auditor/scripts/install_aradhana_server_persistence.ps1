<#
Installs two machine-level Scheduled Tasks for the Billing-PC server:
one at Windows startup and a five-minute watchdog.  Both run as LocalSystem
so they are independent of any employee sign-in.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Watchdog = Join-Path $Root "scripts\aradhana_server_watchdog.ps1"
if (-not (Test-Path -LiteralPath $Watchdog)) { throw "Missing server watchdog script: $Watchdog" }

$TaskCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Watchdog`""

function Register-AradhanaTask([string[]]$Arguments) {
    & schtasks.exe @Arguments | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Scheduled-task registration failed: $($Arguments -join ' ')" }
}

Register-AradhanaTask @("/Create", "/TN", "AradhanaAuditorServer", "/TR", $TaskCommand, "/SC", "ONSTART", "/RU", "SYSTEM", "/RL", "HIGHEST", "/F")
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
Set-ScheduledTask -TaskName "AradhanaAuditorServer" -Settings $settings | Out-Null
if (Get-ScheduledTask -TaskName "AradhanaAuditorServerWatchdog" -ErrorAction SilentlyContinue) {
    & schtasks.exe /Delete /TN "AradhanaAuditorServerWatchdog" /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not remove legacy AradhanaAuditorServerWatchdog task." }
}
& schtasks.exe /Run /TN "AradhanaAuditorServer" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not start AradhanaAuditorServer after installation." }

foreach ($port in 8000, 5173) {
    $name = "Aradhana Payment Auditor TCP $port"
    Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port -Profile Private | Out-Null
}

Write-Host "Installed AradhanaAuditorServer: SYSTEM startup task with a 60-second watchdog."
