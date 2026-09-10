[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,

    [string]$Version = (Get-Date -Format 'yyyy.MM.dd.HHmm')
)

$ErrorActionPreference = 'Stop'

$qrRoot = Split-Path -Parent $PSScriptRoot
$systemsRoot = Split-Path -Parent (Split-Path -Parent $qrRoot)
$routerRoot = Join-Path $systemsRoot 'projects\print-router'
$workflowRoot = Join-Path $systemsRoot 'platform\plugins\document-print-workflow'
$stageRoot = Join-Path $OutputDirectory "AIS-Print-Combo-$Version"

foreach ($path in @($qrRoot, $routerRoot, $workflowRoot)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required component missing: $path" }
}
if (Test-Path -LiteralPath $stageRoot) { throw "Package output already exists: $stageRoot" }

New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null

function Copy-Component([string]$Source, [string]$Destination) {
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    & robocopy $Source $Destination /E /R:1 /W:1 /XD .git __pycache__ .pytest_cache uploads checkins logs data release package AgentWorkspace _merged_from_Aradhana_Projects_copy /XF .env jobs.db *.db *.db-shm *.db-wal *.exe *.disabled *.disabled_on_this_laptop
    if ($LASTEXITCODE -gt 7) { throw "Copy failed ($LASTEXITCODE): $Source" }
}

# Source-only package. Router binaries remain separately signed and staged via
# the approved PC2 deployment share because NPAV may quarantine ad-hoc EXEs.
Copy-Component (Join-Path $qrRoot 'cloud-server') (Join-Path $stageRoot 'qr-cloud-server')
Copy-Component (Join-Path $qrRoot 'local-print-agent') (Join-Path $stageRoot 'qr-print-agent')
Copy-Component $workflowRoot (Join-Path $stageRoot 'document-print-workflow')
Copy-Component $routerRoot (Join-Path $stageRoot 'print-router-source')

$release = @{
    product = 'AIS Print Combo'
    version = $Version
    created_utc = [DateTime]::UtcNow.ToString('o')
    components = @('qr-cloud-server', 'qr-print-agent', 'document-print-workflow', 'print-router-source')
    required_configuration = @(
        'Render: AGENT_TOKEN and QR_REQUIRED_PRINTER must be set.',
        'PC2 print agent: AGENT_TOKEN must match Render; no token value is packaged.',
        'PC2 router: Overlay355TargetPrinterOverride must equal the installed physical 355 queue.',
        'Deploy router EXE only from the approved signed staging share.'
    )
    excluded = @('all tokens', '.env files', 'databases', 'uploads', 'logs', 'executable binaries')
}
$manifestPath = Join-Path $stageRoot 'release-manifest.json'
$release | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding utf8

$hashes = Get-ChildItem -LiteralPath $stageRoot -Recurse -File |
    Get-FileHash -Algorithm SHA256 |
    Select-Object @{ Name = 'path'; Expression = { $_.Path.Substring($stageRoot.Length + 1) } }, Hash
$hashes | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $stageRoot 'sha256.json') -Encoding utf8

Compress-Archive -LiteralPath $stageRoot -DestinationPath "$stageRoot.zip" -CompressionLevel Optimal
Write-Host "Created: $stageRoot"
Write-Host "Archive: $stageRoot.zip"
