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
# The obsolete watchdog was registered ELEVATED, so removing it needs an
# elevated shell -- from a normal one this returns "Access is denied", and
# -ErrorAction SilentlyContinue hid that, leaving the task in place
# (found 2026-09-26). Report it instead of swallowing it; the removal itself
# lives in remove_old_adb_watchdog.ps1, which must be run as administrator.
if (Get-ScheduledTask -TaskName 'CaptureCam_AdbWirelessWatchdog' -ErrorAction SilentlyContinue) {
    try {
        Unregister-ScheduledTask -TaskName 'CaptureCam_AdbWirelessWatchdog' -Confirm:$false -ErrorAction Stop
        Write-Host "Removed obsolete task CaptureCam_AdbWirelessWatchdog."
    } catch {
        Write-Warning ("CaptureCam_AdbWirelessWatchdog is still registered and could not be " +
            "removed ($($_.Exception.Message)). Run tools\remove_old_adb_watchdog.ps1 as administrator.")
    }
}
Start-ScheduledTask -TaskName $TaskName
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
