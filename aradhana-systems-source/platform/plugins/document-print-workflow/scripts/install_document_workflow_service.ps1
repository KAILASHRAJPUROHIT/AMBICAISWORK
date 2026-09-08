param(
    [string]$PythonPath
)
$ErrorActionPreference = 'Stop'
$pluginRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot 'run_document_workflow_service.ps1'
if (-not $PythonPath) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe')
    )
    $PythonPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not (Test-Path -LiteralPath $PythonPath)) { throw "Python not found: $PythonPath" }
if (-not (Test-Path -LiteralPath $runner)) { throw "AIS workflow runner missing: $runner" }
& $PythonPath -c "import flask" 2>$null
if ($LASTEXITCODE -ne 0) { throw "Flask is missing from this Python runtime: $PythonPath. Install it in that exact runtime before deployment." }
$taskName = 'AISDocumentWorkflowApi'

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" -PythonPath `"$PythonPath`"" -WorkingDirectory $pluginRoot
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 365)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'AIS Document Print Workflow local API' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
$deadline = (Get-Date).AddSeconds(20)
do {
    Start-Sleep -Milliseconds 750
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:8310/health' -TimeoutSec 2
        if ($health.status -eq 'healthy') {
            Write-Host "Installed and verified $taskName. API: http://127.0.0.1:8310" -ForegroundColor Green
            exit 0
        }
    } catch { }
} while ((Get-Date) -lt $deadline)
$taskInfo = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
throw "AISDocumentWorkflowApi did not become healthy within 20 seconds. LastTaskResult=$($taskInfo.LastTaskResult). Check $env:ProgramData\AradhanaSystems\logs\document-workflow\workflow-api.log"
