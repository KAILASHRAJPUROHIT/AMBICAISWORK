[CmdletBinding()]
param(
    [string]$TaskName = "AradhanaOutputToOrnItemImageMirror",
    [string]$ToolDirectory = "",
    [string]$PythonwPath = "$env:LOCALAPPDATA\Programs\Python\Python310\pythonw.exe"
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($ToolDirectory)) {
    $ToolDirectory = Split-Path -Parent $PSScriptRoot
}
$toolRoot = (Resolve-Path -LiteralPath $ToolDirectory).Path
$worker = Join-Path $toolRoot "tools\mirror_output_to_orn_item_image.py"
if (-not (Test-Path -LiteralPath $worker -PathType Leaf)) {
    throw "Mirror worker not found: $worker"
}
if (-not (Test-Path -LiteralPath $PythonwPath -PathType Leaf)) {
    $found = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if (-not $found) { throw "pythonw.exe not found. Supply -PythonwPath." }
    $PythonwPath = $found.Source
}

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $PythonwPath -Argument ('"' + $worker + '" --watch') -WorkingDirectory $toolRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Days 3650) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
    -Description "Mirrors JewelleryCatalogTool output images to the Ornate NX image share every second." -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State, Principal
