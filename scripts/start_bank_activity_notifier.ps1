[CmdletBinding()]
param(
    [string]$ServerUrl = "http://127.0.0.1:8000/api/bank-activity",
    [switch]$Configure
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = "C:\Users\kaila\AppData\Local\Programs\Python\Python311\pythonw.exe"
$pythonInteractive = "C:\Users\kaila\AppData\Local\Programs\Python\Python311\python.exe"
$script = Join-Path $root "scripts\bank_activity_notifier.py"
$configScript = Join-Path $root "scripts\configure_bank_activity_notifier.py"
if (-not (Test-Path $python)) { throw "Python runtime not found: $python" }
$env:BANK_ACTIVITY_URL = $ServerUrl
if ($Configure) {
    if (-not (Test-Path $pythonInteractive)) { throw "Interactive Python runtime not found: $pythonInteractive" }
    Start-Process -FilePath $pythonInteractive -ArgumentList "`"$configScript`"" -WorkingDirectory $root -Wait
    exit
}
Start-Process -FilePath $python -ArgumentList "`"$script`"" -WorkingDirectory $root -WindowStyle Hidden
Write-Output "Bank Activity native notifier started."
