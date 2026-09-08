<# Read-only readiness check for the three-node Auditor HA migration. #>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Cluster = Get-Content (Join-Path $Root "config\ha\cluster.json") -Raw | ConvertFrom-Json
$LocalName = $env:COMPUTERNAME.ToUpperInvariant()
$LocalNode = @($Cluster.nodes | Where-Object { $_.hostname -eq $LocalName }) | Select-Object -First 1

if (-not $LocalNode) {
    Write-Output "FAIL: $LocalName is not a configured HA node."
    exit 1
}

$Ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object IPAddress)
$IpOk = $Ips -contains $LocalNode.expected_ipv4
$Postgres = @(Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^postgres' })
$FreeGb = [math]::Round(((Get-PSDrive -Name ($Root.Substring(0,1))).Free / 1GB), 1)

[pscustomobject]@{
    node = $LocalNode.id
    hostname = $LocalName
    expected_ipv4 = $LocalNode.expected_ipv4
    current_ipv4_matches = $IpOk
    free_disk_gb = $FreeGb
    postgresql_service_present = $Postgres.Count -gt 0
    application_port = $Cluster.ports.application
    postgresql_port = $Cluster.ports.postgresql
} | ConvertTo-Json

foreach ($peer in $Cluster.nodes | Where-Object { $_.id -ne $LocalNode.id }) {
    $smb = Test-NetConnection $peer.hostname -Port 445 -InformationLevel Quiet -WarningAction SilentlyContinue
    $pg = Test-NetConnection $peer.hostname -Port $Cluster.ports.postgresql -InformationLevel Quiet -WarningAction SilentlyContinue
    Write-Output ("PEER {0}: SMB={1}; PostgreSQL={2}" -f $peer.hostname, $smb, $pg)
}

if (-not $IpOk) { Write-Output "WARN: expected node IP is not active. Create DHCP reservations before HA activation." }
if ($FreeGb -lt 20) { Write-Output "WARN: less than 20 GB free; do not install a database replica yet." }
