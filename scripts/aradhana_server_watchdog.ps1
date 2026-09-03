<# Keeps the Billing-PC server available after child-process crashes. #>
[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Control = Join-Path $Root "scripts\aradhana_service_control.ps1"
$LogDir = Join-Path $Root "logs\production"
$LogFile = Join-Path $LogDir "watchdog.log"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

while ($true) {
    try {
        $stamp = Get-Date -Format s
        Add-Content -Encoding UTF8 -Path $LogFile -Value "[$stamp] watchdog health cycle"
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Control start-prod *>> $LogFile
    }
    catch {
        Add-Content -Encoding UTF8 -Path $LogFile -Value "[$(Get-Date -Format s)] watchdog error: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds 60
}
