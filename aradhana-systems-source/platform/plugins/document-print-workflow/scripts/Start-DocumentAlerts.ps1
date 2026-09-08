[CmdletBinding()]
param(
    [string]$PythonPath = (Get-Command python -ErrorAction Stop).Source,
    [string]$ScannerApi = 'https://print.aradhanajewellers.com',
    [int]$PollSeconds = 5
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$pluginRoot = Split-Path -Parent $PSScriptRoot
$agent = Join-Path $pluginRoot 'bridge\document_alert_notifier.py'
$secretPath = Join-Path $env:LOCALAPPDATA 'Aradhana\Secrets\document_bridge_token.dpapi'
if (-not (Test-Path -LiteralPath $PythonPath)) { throw "Python not found: $PythonPath" }
if (-not (Test-Path -LiteralPath $agent)) { throw "Document alert agent missing: $agent" }
if (-not (Test-Path -LiteralPath $secretPath)) { throw 'Bridge credential is not configured for this Windows user. Run Set-AISDocumentBridgeToken.ps1 once.' }

$encrypted = [IO.File]::ReadAllBytes($secretPath)
$token = [Text.Encoding]::Unicode.GetString([Security.Cryptography.ProtectedData]::Unprotect($encrypted, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)).Trim()
if ([string]::IsNullOrWhiteSpace($token)) { throw 'Bridge credential could not be decrypted for this Windows user.' }
$existing = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" | Where-Object { $_.CommandLine -like "*document_alert_notifier.py*" }
if ($existing) { Write-Host 'Document alerts are already running for this user.' -ForegroundColor Yellow; exit 0 }

$env:AIS_DOCUMENT_BRIDGE_TOKEN = $token
$pythonWindowless = Join-Path (Split-Path -Parent $PythonPath) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonWindowless)) { $pythonWindowless = $PythonPath }
Start-Process -FilePath $pythonWindowless -ArgumentList @($agent, '--scanner-api', $ScannerApi, '--poll-seconds', $PollSeconds) -WindowStyle Hidden
Remove-Item Env:AIS_DOCUMENT_BRIDGE_TOKEN -ErrorAction SilentlyContinue
Write-Host 'Document alerts started for this signed-in PC. New QR documents appear top-right.' -ForegroundColor Green
