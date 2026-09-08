param(
    [string]$PythonPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$runner = Join-Path $root 'control-center\scripts\run_ais_control_center.ps1'
if (-not $PythonPath) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        'C:\Users\kaila\AppData\Local\Programs\Python\Python311\python.exe'
    ) | Select-Object -Unique
    $PythonPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not (Test-Path -LiteralPath $PythonPath)) { throw "Python not found: $PythonPath" }
& $PythonPath -c "import flask" 2>$null
if ($LASTEXITCODE -ne 0) { throw "Flask is missing from this Python runtime: $PythonPath" }
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" -PythonPath `"$PythonPath`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 365)
Register-ScheduledTask -TaskName 'AISControlCenter' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'AIS local control center' -Force | Out-Null
Start-ScheduledTask -TaskName 'AISControlCenter'
$deadline = (Get-Date).AddSeconds(20)
do {
    Start-Sleep -Milliseconds 750
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:8120/health' -TimeoutSec 2
        if ($health.status -eq 'healthy') {
            Write-Host 'AIS Control Center installed and verified at http://127.0.0.1:8120' -ForegroundColor Green
            exit 0
        }
    } catch { }
} while ((Get-Date) -lt $deadline)
$taskInfo = Get-ScheduledTaskInfo -TaskName 'AISControlCenter' -ErrorAction SilentlyContinue
throw "AIS Control Center did not become healthy. LastTaskResult=$($taskInfo.LastTaskResult). Check $env:ProgramData\AradhanaSystems\logs\ais-control-center\control-center.log"
