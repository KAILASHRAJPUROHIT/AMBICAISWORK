[CmdletBinding()]
param(
    [Parameter(Mandatory)] [ValidatePattern('^[A-Za-z0-9_-]+$')] [string]$Target,
    [Parameter(Mandatory)] [ValidatePattern('^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$')] [string]$Version,
    [Parameter(Mandatory)] [string]$SourceRoot,
    [Parameter(Mandatory)] [string[]]$Include,
    [Parameter(Mandatory)] [string]$ApplyScript,
    [string]$OutputRoot = 'C:\AradhanaSystems\releases'
)

$ErrorActionPreference = 'Stop'
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path.TrimEnd('\')
$ApplyScript = (Resolve-Path -LiteralPath $ApplyScript).Path
if (-not (Test-Path -LiteralPath $ApplyScript -PathType Leaf)) { throw "Apply script missing: $ApplyScript" }
$releaseRoot = Join-Path $OutputRoot "$Target-$Version"
if (Test-Path -LiteralPath $releaseRoot) { throw "Release directory already exists: $releaseRoot" }
$payloadRoot = Join-Path $releaseRoot 'payload'
New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null

$files = [System.Collections.Generic.List[object]]::new()
foreach ($relative in $Include) {
    if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)') { throw "Unsafe include path: $relative" }
    $source = Join-Path $SourceRoot $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Included file missing: $source" }
    $destination = Join-Path $payloadRoot $relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination
    $files.Add([pscustomobject]@{ path = $relative.Replace('\','/'); sha256 = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() })
}
Copy-Item -LiteralPath $ApplyScript -Destination (Join-Path $payloadRoot 'apply.ps1')
$files.Add([pscustomobject]@{ path = 'apply.ps1'; sha256 = (Get-FileHash -LiteralPath (Join-Path $payloadRoot 'apply.ps1') -Algorithm SHA256).Hash.ToLowerInvariant() })
$manifest = [ordered]@{
    schema = 1
    target = $Target
    version = $Version
    created_at = (Get-Date).ToUniversalTime().ToString('o')
    source_root = $SourceRoot
    files = $files
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $payloadRoot 'ais-release.json') -Encoding UTF8
$zip = Join-Path $releaseRoot "$Target-$Version.zip"
Compress-Archive -Path (Join-Path $payloadRoot '*') -DestinationPath $zip -CompressionLevel Optimal
[pscustomobject]@{ Target = $Target; Version = $Version; Bundle = $zip; Files = $files.Count; Sha256 = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash }
