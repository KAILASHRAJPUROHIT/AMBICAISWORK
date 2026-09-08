[CmdletBinding()]
param(
    [string]$PythonPath = (Get-Command python -ErrorAction Stop).Source,
    [switch]$RequireApi
)

$ErrorActionPreference = 'Stop'
$pluginRoot = Split-Path -Parent $PSScriptRoot
$required = @(
    'ais.plugin.json', 'service\app.py', 'bridge\biller_popup.py',
    'bridge\qr_bundle_sync.py', 'bridge\cache_bundle.py',
    'bridge\queue_standalone.py', 'bridge\document_alert_notifier.py',
    'renderer\p355_document_renderer.py', 'scripts\run_document_workflow_service.ps1',
    'scripts\Start-DocumentAlerts.ps1'
)
$missing = $required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $pluginRoot $_)) }
if ($missing) { throw "Workflow deployment is incomplete: $($missing -join ', ')" }
& $PythonPath -c "import flask, pymupdf" 2>$null
if ($LASTEXITCODE -ne 0) { throw "Required Python modules missing in: $PythonPath" }
$api = 'not_checked'
if ($RequireApi) {
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:8310/health' -TimeoutSec 3
        if ($health.status -ne 'healthy') { throw "Health status: $($health.status)" }
        $api = 'healthy'
    } catch { throw "Workflow API health failed: $($_.Exception.Message)" }
}
[pscustomobject]@{ Status = 'ready'; PluginRoot = $pluginRoot; Python = $PythonPath; Api = $api; CheckedAt = (Get-Date).ToUniversalTime().ToString('o') }
