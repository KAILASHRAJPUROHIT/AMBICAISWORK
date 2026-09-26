# Removes the obsolete CaptureCam_AdbWirelessWatchdog scheduled task.
# Superseded by CaptureCam_TabletWatcher (tools/tablet_watcher.ps1). The old
# task targets a phone at 192.168.0.6 that is no longer in use, and an earlier
# version of its script restarted the TABLET's adbd every 30s, which closed
# scrcpy and rotated Android's wireless-debugging TLS port.
#
# Must run ELEVATED: the task was registered with elevation, so deleting it
# returns "Access is denied" from a normal shell.
$ErrorActionPreference = 'Continue'
$log = Join-Path $PSScriptRoot '..\logs\task_removal.txt'
$lines = @("run at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
$lines += "elevated: " + ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

try {
    Unregister-ScheduledTask -TaskName 'CaptureCam_AdbWirelessWatchdog' -Confirm:$false -ErrorAction Stop
    $lines += 'Unregister-ScheduledTask: OK'
} catch {
    $lines += 'Unregister-ScheduledTask failed: ' + $_.Exception.Message
    # schtasks.exe is a second route; it reports its own error text.
    $out = & schtasks.exe /Delete /TN 'CaptureCam_AdbWirelessWatchdog' /F 2>&1
    $lines += 'schtasks /Delete: ' + ($out -join ' | ')
}

$still = Get-ScheduledTask -TaskName 'CaptureCam_AdbWirelessWatchdog' -ErrorAction SilentlyContinue
$lines += if ($still) { 'RESULT: STILL PRESENT' } else { 'RESULT: GONE' }
$lines | Out-File -FilePath $log -Encoding utf8
$lines | Write-Host
