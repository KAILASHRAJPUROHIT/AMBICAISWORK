[CmdletBinding()]
param(
    [string]$PythonPath = 'C:\Users\kaila\AppData\Local\Programs\Python\Python311\python.exe'
)

$ErrorActionPreference = 'Stop'
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this installer from an elevated Administrator PowerShell window.'
}
$platformRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $platformRoot 'ota-control\install_ais_ota_server.ps1') -PythonPath $PythonPath
& (Join-Path $platformRoot 'control-center\scripts\install_ais_control_center.ps1') -PythonPath $PythonPath
& (Join-Path $PSScriptRoot 'Test-AISControlPlane.ps1')
