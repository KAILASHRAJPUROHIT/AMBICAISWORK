[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$requiredTasks = @('AISOTAServer', 'AISControlCenter')
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$taskVerification = 'health_only_non_admin'
if ($isAdmin) {
    foreach ($taskName in $requiredTasks) {
        if (-not (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue)) { throw "AIS task missing: $taskName" }
    }
    $taskVerification = 'verified_admin'
}
$ota = Invoke-RestMethod 'http://192.168.0.12:8091/health' -TimeoutSec 3
if ($ota.status -ne 'healthy' -or -not $ota.public_certificate) { throw 'AIS OTA health check failed.' }
$console = Invoke-RestMethod 'http://127.0.0.1:8120/health' -TimeoutSec 3
if ($console.status -ne 'healthy') { throw 'AIS Control Center health check failed.' }
$rule = Get-NetFirewallRule -DisplayName 'AIS OTA LAN only (TCP 8091)' -ErrorAction SilentlyContinue
if (-not $rule -or $rule.Enabled -ne 'True') { throw 'AIS OTA LAN firewall rule is missing or disabled.' }
[pscustomobject]@{
    Status = 'healthy'
    OTA = 'http://192.168.0.12:8091'
    ControlCenter = 'http://127.0.0.1:8120'
    Tasks = $requiredTasks -join ', '
    TaskVerification = $taskVerification
    CheckedAt = (Get-Date).ToUniversalTime().ToString('o')
}
