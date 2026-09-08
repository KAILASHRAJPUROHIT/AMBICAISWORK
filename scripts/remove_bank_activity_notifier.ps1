$ErrorActionPreference = "Stop"
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw "Run as Administrator." }
foreach ($task in "AradhanaBankActivityNotifier", "AradhanaBankActivityNotifierUser", "AradhanaAuditorAlwaysOn") { Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue }
Get-NetFirewallRule -DisplayName "Aradhana Auditor LAN *" -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
$settings = Join-Path $env:APPDATA "AradhanaBankActivityNotifier"
$localInstall = Join-Path $env:LOCALAPPDATA "AradhanaBankActivityNotifier"
if (Test-Path $settings) { Remove-Item -LiteralPath $settings -Recurse -Force }
if (Test-Path $localInstall) { Remove-Item -LiteralPath $localInstall -Recurse -Force }
Get-CimInstance Win32_Process -Filter "name = 'pythonw.exe'" | Where-Object { $_.CommandLine -like "*bank_activity_notifier.py*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Write-Host "Aradhana Bank Activity notifier, tasks, settings, and firewall rules removed."
