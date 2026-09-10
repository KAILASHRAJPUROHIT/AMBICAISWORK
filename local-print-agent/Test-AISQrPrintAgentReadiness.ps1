[CmdletBinding()]
param(
    [string]$AgentRoot = $PSScriptRoot,
    [string]$TaskName = 'AISQrPrintAgent'
)

$ErrorActionPreference = 'Stop'
$agentRoot = (Resolve-Path -LiteralPath $AgentRoot).Path
$envPath = Join-Path $agentRoot '.env'
if (-not (Test-Path -LiteralPath $envPath)) { throw ".env is missing: $envPath" }
$settings = @{}
foreach ($line in Get-Content -LiteralPath $envPath) {
    if ($line -match '^\s*([^#=\s]+)\s*=\s*(.*)$') { $settings[$matches[1]] = $matches[2].Trim() }
}
$required = @('CLOUD_SERVER_URL', 'AGENT_TOKEN', 'SUMATRA_PATH')
$missing = $required | Where-Object { [string]::IsNullOrWhiteSpace($settings[$_]) }
if ($missing) { throw ".env is incomplete: $($missing -join ', ')" }
if (-not (Test-Path -LiteralPath $settings.SUMATRA_PATH)) { throw 'Configured SumatraPDF executable is missing.' }

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
try {
    $response = Invoke-RestMethod -Uri ($settings.CLOUD_SERVER_URL.TrimEnd('/') + '/api/agent/jobs/pending') -Headers @{ Authorization = "Bearer $($settings.AGENT_TOKEN)" } -TimeoutSec 12
} catch {
    throw "Authenticated cloud agent check failed: $($_.Exception.Message)"
}
if ($null -eq $response.jobs) { throw 'Cloud agent endpoint returned an invalid response.' }

[pscustomobject]@{
    Status = 'ready-for-controlled-cutover'
    TaskName = $task.TaskName
    TaskState = $task.State
    CloudServer = $settings.CLOUD_SERVER_URL
    PendingJobs = @($response.jobs).Count
    ConfiguredPrinter = $settings.PRINTER_NAME
    CheckedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
}
