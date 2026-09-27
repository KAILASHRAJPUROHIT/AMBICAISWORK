[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Serial,
    [Parameter(Mandatory)] [string] $ApkPath,
    [string] $ServerUrl = 'https://mdm.ambicdigital.in'
)

$ErrorActionPreference = 'Stop'
$Package = 'com.mdmesh.agent.cn'
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
    Write-Host 'AMBIC China agent is already Device Owner; not reassigning it.'
} else {
    Invoke-Adb @('install', '-r', $ApkPath)
    Invoke-Adb @('shell', 'dpm', 'set-device-owner', $Admin)
}

# One-time, silent grant of the WRITE_SETTINGS appop. This is what lets the on-device
# quick-controls panel (auto-rotation, brightness) write Settings.System directly for the
# rest of this device's life with ZERO Settings.ACTION_MANAGE_WRITE_SETTINGS prompt ever
# shown -- the whole point being that the kiosked end user never sees a route into the
# real Settings app. `pm grant` cannot touch this (WRITE_SETTINGS is an appop, not a
# runtime permission); `appops set` is the correct tool, and must run now, at the same
# ADB moment Device Owner itself is assigned, before the device reaches an end user.
# Flight mode does NOT need this: it goes through DevicePolicyManager.setGlobalSetting(),
# which Device Owner already holds without any extra grant.
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
