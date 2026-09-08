param(
    [Parameter(Mandatory = $true)][string]$PythonPath
)

$ErrorActionPreference = 'Stop'
$pluginRoot = Split-Path -Parent $PSScriptRoot
$appPath = Join-Path $pluginRoot 'service\app.py'
if (-not (Test-Path -LiteralPath $PythonPath)) { throw "Python not found: $PythonPath" }
if (-not (Test-Path -LiteralPath $appPath)) { throw "AIS workflow app missing: $appPath" }

$env:AIS_DOCUMENT_WORKFLOW_DB = Join-Path $pluginRoot 'service\document_workflow.db'
$env:AIS_DOCUMENT_WORKFLOW_PORT = '8310'
$logRoot = Join-Path $env:ProgramData 'AradhanaSystems\logs\document-workflow'
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$logPath = Join-Path $logRoot 'workflow-api.log'
"[$((Get-Date).ToUniversalTime().ToString('o'))] starting AISDocumentWorkflowApi with $PythonPath" | Add-Content -LiteralPath $logPath -Encoding UTF8
& $PythonPath $appPath *>> $logPath
exit $LASTEXITCODE
