$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = "C:\Users\kaila\AppData\Local\Programs\Python\Python311\pythonw.exe"
$script = Join-Path $root "scripts\bank_activity_notifier.py"
if (-not (Test-Path $python)) { throw "Python runtime not found: $python" }
Start-Process -FilePath $python -ArgumentList "`"$script`"" -WorkingDirectory $root -WindowStyle Hidden
Write-Output "Bank Activity native notifier started."
