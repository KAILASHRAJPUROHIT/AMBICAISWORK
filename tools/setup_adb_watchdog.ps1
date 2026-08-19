# One-time setup: registers adb_wireless_watchdog.ps1 as a Windows
# Scheduled Task that starts at user logon and restarts automatically if
# it ever exits, so wireless adb to the CaptureCam phone comes back on its
# own after this PC reboots (and re-arms itself the moment the phone is
# next seen over USB, e.g. plugged in for charging).

$TaskName = "CaptureCam_AdbWirelessWatchdog"
$ScriptPath = Join-Path $PSScriptRoot "adb_wireless_watchdog.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 0)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Keeps wireless adb to the CaptureCam phone (192.168.0.6:5555) reconnected after PC/phone reboots." `
    -Force

Write-Host "Registered scheduled task '$TaskName'. Starting it now..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 2
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
