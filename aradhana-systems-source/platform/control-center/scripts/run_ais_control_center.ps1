param(
    [Parameter(Mandatory = $true)] [string]$PythonPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$app = Join-Path $root 'control-center\app.py'
if (-not (Test-Path -LiteralPath $PythonPath)) { throw "Python not found: $PythonPath" }
if (-not (Test-Path -LiteralPath $app)) { throw "AIS Control Center app missing: $app" }
$logRoot = Join-Path $env:ProgramData 'AradhanaSystems\logs\ais-control-center'
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$logPath = Join-Path $logRoot 'control-center.log'
# Flask writes normal lifecycle messages to stderr. Redirect in cmd.exe so
# ErrorActionPreference cannot turn those messages into a task failure.
$command = '""{0}" "{1}" 1>>"{2}" 2>>&1"' -f $PythonPath, $app, $logPath
& $env:ComSpec /d /c $command
$code = $LASTEXITCODE
"[$((Get-Date).ToUniversalTime().ToString('o'))] AIS Control Center process exited with code $code" | Add-Content -LiteralPath $logPath -Encoding UTF8
exit $code
