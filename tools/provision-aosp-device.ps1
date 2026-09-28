# Enrolls a device WITHOUT Google Play (e.g. China-ROM Redmi) over USB, since those can't use
# Android Enterprise QR provisioning. Since 2026-09-28 the global and China agents are unified:
# pass the normal release-signed APK (mdmesh-agent.apk from the GitHub release) -- the same
# package, signing key and console rollout as every other device. Requires a factory-reset device
# with no accounts, USB debugging on, and a fresh single-use enrollment token from the console.
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Serial,
    [Parameter(Mandatory)] [string] $ApkPath,
    [string] $ServerUrl = 'https://mdm.ambicdigital.in'
)

$ErrorActionPreference = 'Stop'
$Package = 'com.mdmesh.agent'
$Admin = "$Package/.admin.AdminReceiver"
$Bootstrap = "$Package/.provisioning.AospUsbBootstrapActivity"

function Invoke-Adb([string[]] $Arguments) {
    & adb -s $Serial @Arguments
    if ($LASTEXITCODE -ne 0) { throw "adb failed: $($Arguments -join ' ')" }
}

if (-not (Test-Path -LiteralPath $ApkPath -PathType Leaf)) {
    throw "APK not found: $ApkPath"
}
if ($ServerUrl -notmatch '^https://[^/]+') {
    throw 'ServerUrl must be an HTTPS origin.'
}

$state = (& adb devices) -match "^$([regex]::Escape($Serial))\s+device$"
if (-not $state) { throw "Device $Serial is not connected/authorized in adb." }

$owners = (& adb -s $Serial shell dpm list-owners 2>&1) -join "`n"
if ($owners -match 'Device Owner:') {
    if ($owners -notmatch [regex]::Escape($Package)) {
        throw "Refusing: device already has another Device Owner. No changes made."
    }
    Write-Host 'AMBIC agent is already Device Owner; not reassigning it.'
} else {
    Invoke-Adb @('install', '-r', $ApkPath)
    Invoke-Adb @('shell', 'dpm', 'set-device-owner', $Admin)
}

# Initial grant of the WRITE_SETTINGS appop -- needed ONLY for auto-rotation. Android resets it on
# every agent update; the shop PC's tools/appop-guardian.py re-grants it automatically after that
# (docs/WRITE_SETTINGS-PERSISTENCE.md). Original rationale:
# (Settings.System.ACCELEROMETER_ROTATION has no DevicePolicyManager allow-list entry, confirmed
# against DevicePolicyManagerService.SYSTEM_SETTINGS_ALLOWLIST in AOSP master, so it's the one
# quick-controls toggle still requiring a real Settings.System write). Brightness (both the
# auto/manual mode and the level) goes through DevicePolicyManager.setSystemSetting() instead,
# which IS on that allow-list -- no appop, no ADB step, works on every already-enrolled device
# including ones with no ADB moment (QR/GMS provisioning) ever available.
# `pm grant` cannot touch WRITE_SETTINGS (it's an appop, not a runtime permission); `appops set`
# is the correct tool, and must run now, at the same ADB moment Device Owner itself is assigned,
# before the device reaches an end user -- that's what keeps this out of
# Settings.ACTION_MANAGE_WRITE_SETTINGS entirely.
Invoke-Adb @('shell', 'appops', 'set', $Package, 'WRITE_SETTINGS', 'allow')

$secureToken = Read-Host 'Paste a fresh single-use enrollment token' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    if ([string]::IsNullOrWhiteSpace($token)) { throw 'Enrollment token is required.' }
    Invoke-Adb @('shell', 'am', 'start', '-n', $Bootstrap, '--es', 'com.mdmesh.aosp.SERVER_URL', $ServerUrl, '--es', 'com.mdmesh.aosp.ENROLL_TOKEN', $token)
} finally {
    if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    Remove-Variable token -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 3
Invoke-Adb @('shell', 'dpm', 'list-owners')
Write-Host 'Bootstrap submitted. Verify the device appears in AMBIC MDM before disconnecting USB.'
Write-Host ''
Write-Host 'Last step (one time): on the device, Developer options > Wireless debugging > on, accept'
Write-Host '"always allow on this network", then "Pair device with pairing code" and run on this PC:'
Write-Host '    adb pair <ip>:<port> <code>'
Write-Host 'That trusts the shop Wi-Fi so the agent keeps wireless debugging on by itself from then on.'
