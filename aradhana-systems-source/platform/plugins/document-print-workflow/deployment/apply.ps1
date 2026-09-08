[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$ReleaseRoot,
    [string]$PythonPath
)

$ErrorActionPreference = 'Stop'
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Document workflow deployment requires an elevated PowerShell session.'
}

$ReleaseRoot = (Resolve-Path -LiteralPath $ReleaseRoot).Path
$target = 'C:\AradhanaSystems\platform\plugins\document-print-workflow'
$backupRoot = Join-Path $env:ProgramData ('AradhanaSystems\backups\document-workflow\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$files = @(
    'ais.plugin.json', 'README.md',
    'service\app.py',
    'bridge\biller_popup.py', 'bridge\qr_bundle_sync.py', 'bridge\cache_bundle.py',
    'bridge\queue_standalone.py', 'bridge\document_alert_notifier.py',
    'renderer\p355_document_renderer.py',
    'scripts\run_document_workflow_service.ps1', 'scripts\install_document_workflow_service.ps1',
    'scripts\install_document_alerts_startup.ps1', 'scripts\Start-DocumentAlerts.ps1',
    'scripts\Set-AISDocumentBridgeToken.ps1', 'scripts\Test-DocumentWorkflowDeployment.ps1',
    'contracts\print-session.v1.json'
)
foreach ($relative in $files) {
    if (-not (Test-Path -LiteralPath (Join-Path $ReleaseRoot $relative) -PathType Leaf)) { throw "Release payload incomplete: $relative" }
}

if (Get-ScheduledTask -TaskName 'AISDocumentWorkflowApi' -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName 'AISDocumentWorkflowApi' -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}
foreach ($relative in $files) {
    $destination = Join-Path $target $relative
    if (Test-Path -LiteralPath $destination -PathType Leaf) {
        $backup = Join-Path $backupRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backup) | Out-Null
        Copy-Item -LiteralPath $destination -Destination $backup -Force
    }
}
foreach ($relative in $files) {
    $destination = Join-Path $target $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item -LiteralPath (Join-Path $ReleaseRoot $relative) -Destination $destination -Force
}

if (-not $PythonPath) { $PythonPath = (Get-Command python -ErrorAction Stop).Source }
& (Join-Path $target 'scripts\install_document_workflow_service.ps1') -PythonPath $PythonPath
& (Join-Path $target 'scripts\install_document_alerts_startup.ps1') -PythonPath $PythonPath
& (Join-Path $target 'scripts\Test-DocumentWorkflowDeployment.ps1') -PythonPath $PythonPath -RequireApi
[pscustomobject]@{ Status = 'applied'; Target = $target; Backup = $backupRoot; CheckedAt = (Get-Date).ToUniversalTime().ToString('o') }
