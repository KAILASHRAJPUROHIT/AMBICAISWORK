[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$AwsPublicKey,
    [Parameter(Mandatory)][string]$AwsEndpoint
)

$ErrorActionPreference = 'Stop'
$tunnelName = 'server2k22-rtgs'
$wireGuardExe = Join-Path $env:ProgramFiles 'WireGuard\wg.exe'
$wireGuardUi = Join-Path $env:ProgramFiles 'WireGuard\wireguard.exe'
$keyRoot = 'C:\ProgramData\AMBIC DIGITAL\WireGuard'
$privateKeyPath = Join-Path $keyRoot 'server2k22-private.key'
$publicKeyPath = Join-Path $keyRoot 'server2k22-public.key'
$configPath = Join-Path $keyRoot "$tunnelName.conf"

if (-not (Test-Path -LiteralPath $wireGuardExe) -or -not (Test-Path -LiteralPath $wireGuardUi)) {
    throw 'Install WireGuard for Windows from wireguard.com/install before running this script.'
}

New-Item -ItemType Directory -Path $keyRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $privateKeyPath)) {
    $privateKey = & $wireGuardExe genkey
    $privateKey | Set-Content -LiteralPath $privateKeyPath -NoNewline -Encoding ascii
    $privateKey | & $wireGuardExe pubkey | Set-Content -LiteralPath $publicKeyPath -NoNewline -Encoding ascii
}

$privateKey = (Get-Content -LiteralPath $privateKeyPath -Raw).Trim()
$publicKey = (Get-Content -LiteralPath $publicKeyPath -Raw).Trim()

@"
[Interface]
PrivateKey = $privateKey
Address = 10.241.77.2/32

[Peer]
PublicKey = $AwsPublicKey
Endpoint = $AwsEndpoint`:51820
AllowedIPs = 10.241.77.0/24
PersistentKeepalive = 25
"@ | Set-Content -LiteralPath $configPath -Encoding ascii

if (-not (Get-NetFirewallRule -DisplayName 'AMBIC RTGS WireGuard SMB from AWS only' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName 'AMBIC RTGS WireGuard SMB from AWS only' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 445 -RemoteAddress 10.241.77.1 -Profile Any | Out-Null
}
& $wireGuardUi /installtunnelservice $configPath

Write-Host "Server2k22 WireGuard public key: $publicKey"
Write-Host 'Give only this public key to the AWS peer setup script.'
