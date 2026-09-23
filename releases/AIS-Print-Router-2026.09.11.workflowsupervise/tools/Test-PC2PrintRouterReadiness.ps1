[CmdletBinding()]
param(
    [string]$ConfigPath = 'C:\ProgramData\Aradhana\OrnateAutoPrintTray\config.txt',
    [string]$WorkflowApi = 'http://127.0.0.1:8310/health'
)

$ErrorActionPreference = 'Stop'

function Get-ConfigValue([string]$Key, [string[]]$Lines) {
    $match = $Lines | Where-Object { $_ -match "^$([regex]::Escape($Key))=" } | Select-Object -First 1
    if (-not $match) { return $null }
    return $match.Substring($Key.Length + 1)
}

if (-not (Test-Path -LiteralPath $ConfigPath)) { throw "Router config is missing: $ConfigPath" }
$configLines = Get-Content -LiteralPath $ConfigPath
$requiredConfig = @('MasterEnabled', 'Copy1Printer', 'Copy2Printer', 'DocumentWorkflowEnabled', 'DocumentWorkflowRoot', 'DocumentWorkflowApi')
$config = @{}
foreach ($key in $requiredConfig + 'Overlay355TargetPrinterOverride') {
    $config[$key] = Get-ConfigValue $key $configLines
}
$missingConfig = $requiredConfig | Where-Object { [string]::IsNullOrWhiteSpace($config[$_]) }
if ($missingConfig) { throw "Router config is incomplete: $($missingConfig -join ', ')" }
if ($config.MasterEnabled -ne 'true') { throw 'MasterEnabled must be true.' }
if ($config.DocumentWorkflowEnabled -ne 'true') { throw 'DocumentWorkflowEnabled must be true.' }

$router = Get-Process AradhanaOrnateAutoPrint -ErrorAction SilentlyContinue
if (-not $router) { throw 'AradhanaOrnateAutoPrint is not running.' }
if ($router.Count -ne 1) { throw "Expected exactly one router process; found $($router.Count)." }

$installedPrinters = @(Get-Printer | Select-Object -ExpandProperty Name)
$requiredPrinters = @($config.Copy1Printer, $config.Copy2Printer)
if ($config.Overlay355TargetPrinterOverride) { $requiredPrinters += $config.Overlay355TargetPrinterOverride }
$missingPrinters = $requiredPrinters | Where-Object { $_ -notin $installedPrinters }
if ($missingPrinters) { throw "Required printer queue(s) missing: $($missingPrinters -join ', ')" }

$workflowRoot = $config.DocumentWorkflowRoot
$requiredWorkflowFiles = @(
    'service\app.py',
    'bridge\qr_bundle_sync.py',
    'bridge\cache_bundle.py',
    'bridge\claim_bundle_for_bill.py',
    'bridge\biller_popup.py',
    'renderer\p355_document_renderer.py'
)
$missingWorkflow = $requiredWorkflowFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $workflowRoot $_)) }
if ($missingWorkflow) { throw "Workflow installation is incomplete: $($missingWorkflow -join ', ')" }

$tokenPath = Join-Path $env:LOCALAPPDATA 'Aradhana\Secrets\document_bridge_token.dpapi'
if (-not (Test-Path -LiteralPath $tokenPath)) { throw "Encrypted bridge credential is missing for this Windows user: $tokenPath" }

try {
    $health = Invoke-RestMethod -Uri $WorkflowApi -TimeoutSec 4
} catch {
    throw "Workflow API is unreachable at $WorkflowApi : $($_.Exception.Message)"
}
if ($health.status -ne 'healthy') { throw "Workflow API is not healthy: $($health.status)" }

$reference = Join-Path (Split-Path -Parent $ConfigPath) 'office-sales-voucher-format-reference.png'
if (-not (Test-Path -LiteralPath $reference)) { throw "Approved Voucher Format reference is missing: $reference" }

[pscustomobject]@{
    Status = 'ready-for-physical-acceptance-test'
    RouterPid = $router.Id
    Copy1Printer = $config.Copy1Printer
    Copy2Printer = $config.Copy2Printer
    Overlay355Target = $config.Overlay355TargetPrinterOverride
    WorkflowApi = $WorkflowApi
    PendingBundles = $health.pending_bundles
    VoucherFormatReference = $reference
    CheckedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
}
