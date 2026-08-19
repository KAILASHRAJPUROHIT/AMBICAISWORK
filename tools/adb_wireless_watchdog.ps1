# Keeps CaptureCam's phone reachable over wireless adb (port 5555) without
# manual intervention after a PC reboot, and self-heals after a PHONE
# reboot the moment the phone is plugged into this PC via USB.
#
# Why this can't be fully automatic across a PHONE reboot with no USB
# contact at all: Android intentionally does not let a network adb
# listener survive a reboot without a fresh USB confirmation -- that is a
# deliberate security boundary, not a bug or a missing setting. This
# script is the closest practical approximation: it polls, and the instant
# a USB path exists (phone plugged in, e.g. for charging on the capture
# rig) it re-arms wireless adb with no one needing to remember the manual
# `adb tcpip 5555` step. If the phone is unplugged AND rebooted at the
# same time, someone still has to plug it in once.
#
# Run as a Windows Scheduled Task at PC logon (see setup_adb_watchdog.ps1),
# not interactively -- it loops forever.

$ErrorActionPreference = "SilentlyContinue"
$PhoneIp = "192.168.0.6"
$PhonePort = 5555
$LogFile = Join-Path $PSScriptRoot "..\logs\adb_watchdog.log"

function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $LogFile -Value $line
}

while ($true) {
    $target = "$PhoneIp`:$PhonePort"
    $devices = & adb devices 2>$null

    $wirelessUp = $devices -match [regex]::Escape($target) -and $devices -match "device$"
    if (-not $wirelessUp) {
        # Try a plain reconnect first -- cheap, works if the listener is
        # already up but the host-side adb server just doesn't know about
        # it yet (e.g. right after this PC rebooted).
        & adb connect $target 2>$null | Out-Null
        Start-Sleep -Seconds 2
        $devices = & adb devices 2>$null
        $wirelessUp = $devices -match [regex]::Escape($target) -and $devices -match "device$"
    }

    if (-not $wirelessUp) {
        # Reconnect alone didn't work -- the listener itself is down,
        # almost always because the phone rebooted. Only a USB session can
        # re-arm it. Look for any USB-attached device serial (anything in
        # `adb devices` that isn't an ip:port entry).
        $usbSerial = ($devices | Select-String '^\S+\s+device$' | Where-Object { $_ -notmatch [regex]::Escape($target) } | ForEach-Object { ($_ -split '\s+')[0] } | Select-Object -First 1)
        if ($usbSerial) {
            & adb -s $usbSerial tcpip $PhonePort 2>$null | Out-Null
            Start-Sleep -Seconds 2
            & adb connect $target 2>$null | Out-Null
            Start-Sleep -Seconds 1
            $devices = & adb devices 2>$null
            $wirelessUp = $devices -match [regex]::Escape($target) -and $devices -match "device$"
            if ($wirelessUp) {
                Write-Log "Re-armed wireless adb via USB ($usbSerial) -> $target"
            } else {
                Write-Log "USB device $usbSerial present but tcpip re-arm still failed"
            }
        }
    }

    Start-Sleep -Seconds 30
}
