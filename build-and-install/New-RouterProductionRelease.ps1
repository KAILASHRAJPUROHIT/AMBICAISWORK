[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,

    [string]$Version = (Get-Date -Format 'yyyy.MM.dd.HHmm')
)

$ErrorActionPreference = 'Stop'
$buildRoot = $PSScriptRoot
$routerRoot = Split-Path -Parent $buildRoot
$stageRoot = Join-Path $OutputDirectory "AIS-Print-Router-$Version"
$archivePath = "$stageRoot.zip"
$exe = Join-Path $buildRoot 'AradhanaOrnateAutoPrint.exe'
$reference = Join-Path $routerRoot 'assets\office-sales-voucher-format-reference.png'

if (Test-Path -LiteralPath $stageRoot) { throw "Release output already exists: $stageRoot" }
if (Test-Path -LiteralPath $archivePath) { throw "Release archive already exists: $archivePath" }
if (-not (Test-Path -LiteralPath $exe)) { throw "Signed router EXE is missing: $exe" }
if (-not (Test-Path -LiteralPath $reference)) { throw "Voucher Format reference is missing: $reference" }

$signature = Get-AuthenticodeSignature -FilePath $exe
if ($signature.Status -ne 'Valid') { throw "Router EXE signature is not valid: $($signature.Status)" }

New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null
$files = @(
    'AradhanaOrnateAutoPrint.exe',
    'Install_Aradhana_Ornate_AutoPrint.bat',
    'Uninstall_Aradhana_Ornate_AutoPrint.bat',
    'Set_AIS_Document_Bridge_Token.ps1',
    'AradhanaInternalCert.cer',
    'SECURITY_REVIEW_VOUCHER_FORMAT_ROUTER_20260906.md'
)
foreach ($file in $files) {
    $source = Join-Path $buildRoot $file
    if (-not (Test-Path -LiteralPath $source)) { throw "Required release file is missing: $source" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $stageRoot $file) -Force
}
Copy-Item -LiteralPath $reference -Destination (Join-Path $stageRoot 'office-sales-voucher-format-reference.png') -Force
New-Item -ItemType Directory -Path (Join-Path $stageRoot 'tools') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $routerRoot 'tools\Test-PC2PrintRouterReadiness.ps1') -Destination (Join-Path $stageRoot 'tools\Test-PC2PrintRouterReadiness.ps1') -Force

$manifest = [ordered]@{
    product = 'AIS Ornate Print Router'
    version = $Version
    created_utc = [DateTime]::UtcNow.ToString('o')
    signer_subject = $signature.SignerCertificate.Subject
    signer_thumbprint = $signature.SignerCertificate.Thumbprint
    installer_requires = @('Administrator PowerShell', 'Valid Authenticode signature', 'Approved Voucher Format reference')
    notes = @('No token, database, upload, log, or customer document is included.', 'Use only from an approved deployment share. Do not copy a freshly compiled EXE directly to a billing PC.')
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $stageRoot 'release-manifest.json') -Encoding utf8

$hashes = Get-ChildItem -LiteralPath $stageRoot -Recurse -File | Get-FileHash -Algorithm SHA256 |
    Select-Object @{ Name = 'path'; Expression = { $_.Path.Substring($stageRoot.Length + 1) } }, Hash
$hashes | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $stageRoot 'sha256.json') -Encoding utf8
Compress-Archive -LiteralPath $stageRoot -DestinationPath $archivePath -CompressionLevel Optimal
Write-Host "Release directory: $stageRoot"
Write-Host "Release archive: $archivePath"
