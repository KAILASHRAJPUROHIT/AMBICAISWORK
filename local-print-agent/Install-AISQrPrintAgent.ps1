[CmdletBinding()]
param(
    [string]$AgentRoot = $PSScriptRoot,
    [string]$PythonPath,
    [string]$TaskName = 'AISQrPrintAgent'
)

$ErrorActionPreference = 'Stop'
$agentRoot = (Resolve-Path -LiteralPath $AgentRoot).Path
$agentPath = Join-Path $agentRoot 'agent.py'
$envPath = Join-Path $agentRoot '.env'
if (-not (Test-Path -LiteralPath $agentPath)) { throw "agent.py is missing: $agentPath" }
if (-not (Test-Path -LiteralPath $envPath)) { throw ".env is missing: $envPath" }

if (-not $PythonPath) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\pythonw.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\pythonw.exe')
    )
    $PythonPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not (Test-Path -LiteralPath $PythonPath)) { throw "pythonw.exe was not found: $PythonPath" }

$environment = @{}
foreach ($line in Get-Content -LiteralPath $envPath) {
    if ($line -match '^\s*([^#=\s]+)\s*=\s*(.*)$') { $environment[$matches[1]] = $matches[2].Trim() }
}
$requiredKeys = @('CLOUD_SERVER_URL', 'AGENT_TOKEN', 'SUMATRA_PATH')
$missing = $requiredKeys | Where-Object { [string]::IsNullOrWhiteSpace($environment[$_]) }
if ($missing) { throw ".env is incomplete: $($missing -join ', ')" }
if (-not (Test-Path -LiteralPath $environment.SUMATRA_PATH)) { throw 'Configured SUMATRA_PATH does not exist.' }

& $PythonPath -c "import requests, dotenv, fitz, PIL" 2>$null
if ($LASTEXITCODE -ne 0) { throw "Required agent Python modules are missing in: $PythonPath" }

# Printer queues commonly belong to the signed-in Windows user. Do not run
# this process as SYSTEM: that would create a different and unreliable printer
# context. The named task prevents any broad pythonw.exe termination.
$identity = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Highest
$action = New-ScheduledTaskAction -Execute $PythonPath -Argument "`"$agentPath`"" -WorkingDirectory $agentRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 365) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'AIS QR print gateway for the signed-in printer session' -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

[pscustomobject]@{
    Status = 'installed'
    TaskName = $TaskName
    AgentRoot = $agentRoot
    Python = $PythonPath
    CloudServer = $environment.CLOUD_SERVER_URL
    RunAs = $identity
}
