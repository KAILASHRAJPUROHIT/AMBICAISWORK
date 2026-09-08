[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $ServerUrl,
    [Parameter(Mandatory)] [ValidateSet('beta','stable')] [string] $Channel,
    [Parameter(Mandatory)] [string] $Target,
    [switch] $Apply
)
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:ProgramData "AradhanaSystems\updates\$Target"
$statePath = Join-Path $root 'state.json'
$staging = Join-Path $root 'staged'
New-Item -ItemType Directory -Force -Path $staging | Out-Null

function Read-Json([string]$Path, $Fallback) {
    if (Test-Path -LiteralPath $Path) { return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json }
    return $Fallback
}
function Write-Json([string]$Path, $Value) {
    $Value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Path -Encoding UTF8
}
function Assert-ReleasePayload($PayloadRoot, $Target, $Version) {
    $manifestPath = Join-Path $PayloadRoot 'ais-release.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'Signed bundle has no ais-release.json.' }
    $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    if ($manifest.schema -ne 1 -or $manifest.target -ne $Target -or $manifest.version -ne $Version) { throw 'Payload manifest target/version mismatch.' }
    if (-not $manifest.files -or @($manifest.files).Count -eq 0) { throw 'Payload manifest has no files.' }
    $rootFull = [IO.Path]::GetFullPath($PayloadRoot).TrimEnd('\') + '\'
    foreach ($entry in $manifest.files) {
        $relative = [string]$entry.path
        if ([string]::IsNullOrWhiteSpace($relative) -or [IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)') { throw "Unsafe payload path: $relative" }
        $candidate = [IO.Path]::GetFullPath((Join-Path $PayloadRoot $relative))
        if (-not $candidate.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "Payload file missing: $relative" }
        $actualHash = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne ([string]$entry.sha256).ToLowerInvariant()) { throw "Payload file checksum mismatch: $relative" }
    }
}
function Verify-Envelope($Envelope, [byte[]]$CertificateBytes) {
    $payload = [Convert]::FromBase64String([string]$Envelope.payload_b64)
    $signature = [Convert]::FromBase64String([string]$Envelope.signature_b64)
    $certificate = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 -ArgumentList (,$CertificateBytes)
    $rsa = $certificate.PublicKey.Key
    $sha256 = New-Object System.Security.Cryptography.SHA256Managed
    if (-not $rsa.VerifyData($payload, $sha256, $signature)) { throw 'Release signature is invalid.' }
    return [Text.Encoding]::UTF8.GetString($payload) | ConvertFrom-Json
}

$base = $ServerUrl.TrimEnd('/')
$certificatePath = Join-Path $root 'ota-public.cer'
Invoke-WebRequest "$base/v1/public-certificate" -OutFile $certificatePath -UseBasicParsing -TimeoutSec 20
$certificateBytes = [IO.File]::ReadAllBytes($certificatePath)
$envelope = Invoke-RestMethod "$base/v1/releases/$Channel/$Target/current" -TimeoutSec 20
$release = Verify-Envelope $envelope $certificateBytes
if ($release.target -ne $Target -or $release.channel -ne $Channel -or $release.schema -ne 1) { throw 'Release target/channel mismatch.' }
$state = Read-Json $statePath ([pscustomobject]@{ applied_version = ''; staged_version = '' })
if ($state.applied_version -eq $release.version) { Write-Output "Already applied: $($release.version)"; exit 0 }

$file = [string]$release.artifact.filename
if ([IO.Path]::GetFileName($file) -ne $file -or $file -notlike '*.zip') { throw 'Invalid artifact name.' }
$releasePath = Join-Path $staging $release.version
New-Item -ItemType Directory -Force -Path $releasePath | Out-Null
$zipPath = Join-Path $releasePath $file
Invoke-WebRequest "$base/v1/releases/$Channel/$Target/artifacts/$($release.version)/$file" -OutFile $zipPath -UseBasicParsing -TimeoutSec 120
$actual = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne ([string]$release.artifact.sha256).ToLowerInvariant()) { Remove-Item -LiteralPath $zipPath -Force; throw 'Artifact checksum is invalid.' }
$extract = Join-Path $releasePath 'payload'
Remove-Item -LiteralPath $extract -Force -Recurse -ErrorAction SilentlyContinue
Expand-Archive -LiteralPath $zipPath -DestinationPath $extract -Force
Assert-ReleasePayload $extract $Target $release.version
$applyScript = Join-Path $extract 'apply.ps1'
if (-not (Test-Path -LiteralPath $applyScript)) { throw 'Signed bundle has no apply.ps1.' }
Write-Json $statePath ([pscustomobject]@{ applied_version = $state.applied_version; staged_version = $release.version; staged_at = (Get-Date).ToUniversalTime().ToString('o') })
if (-not $Apply) { Write-Output "Verified and staged: $($release.version)"; exit 0 }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $applyScript -ReleaseRoot $extract
if ($LASTEXITCODE -ne 0) { throw "Signed installer failed with exit $LASTEXITCODE." }
Write-Json $statePath ([pscustomobject]@{ applied_version = $release.version; applied_at = (Get-Date).ToUniversalTime().ToString('o'); staged_version = $release.version })
Write-Output "Applied: $($release.version)"
