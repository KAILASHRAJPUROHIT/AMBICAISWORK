# One-time: registers tablet_watcher.ps1 to run at logon as the current user
# (non-elevated -- it needs this user's adb key), restarting if it dies.
# Also removes the obsolete CaptureCam_AdbWirelessWatchdog task, which pointed
# at an old phone (192.168.0.6) and once restarted tablet adbd in a loop.
$TaskName = 'CaptureCam_TabletWatcher'
$Script   = Join-Path $PSScriptRoot 'tablet_watcher.ps1'
$action   = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Script`""
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description 'CaptureCam tablet: feed server + wireless ADB keep-alive + scrcpy on app start.' -Force | Out-Null
Unregister-ScheduledTask -TaskName 'CaptureCam_AdbWirelessWatchdog' -Confirm:$false -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName $TaskName
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
