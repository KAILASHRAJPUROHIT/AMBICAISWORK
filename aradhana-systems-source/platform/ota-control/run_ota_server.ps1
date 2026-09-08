param(
    [Parameter(Mandatory = $true)] [string]$PythonPath,
    [string]$BindAddress = '192.168.0.12',
    [int]$Port = 8091
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path -LiteralPath $PythonPath)) { throw "Python not found: $PythonPath" }
$env:AIS_OTA_ROOT = 'C:\AradhanaSystems\ota-releases'
$logRoot = Join-Path $env:ProgramData 'AradhanaSystems\logs\ais-ota'
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
"[$((Get-Date).ToUniversalTime().ToString('o'))] starting AIS OTA at $BindAddress`:$Port" | Add-Content -LiteralPath (Join-Path $logRoot 'ota-server.log') -Encoding UTF8
$logPath = Join-Path $logRoot 'ota-server.log'
try {
    # Uvicorn writes ordinary lifecycle messages to stderr. Do the redirection
    # in cmd.exe so PowerShell's ErrorActionPreference cannot mistake those
    # messages for a terminating task failure.
    $command = '""{0}" -m uvicorn server:app --host {1} --port {2} --app-dir "{3}" 1>>"{4}" 2>>&1"' -f $PythonPath, $BindAddress, $Port, $root, $logPath
    & $env:ComSpec /d /c $command
    $code = $LASTEXITCODE
    "[$((Get-Date).ToUniversalTime().ToString('o'))] AIS OTA process exited with code $code" | Add-Content -LiteralPath $logPath -Encoding UTF8
    exit $code
} catch {
    "[$((Get-Date).ToUniversalTime().ToString('o'))] AIS OTA launcher exception: $($_ | Out-String)" | Add-Content -LiteralPath $logPath -Encoding UTF8
    throw
}
