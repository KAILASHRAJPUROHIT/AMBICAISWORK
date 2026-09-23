[CmdletBinding()]
param(
    [string]$TaskName = "AradhanaOrnItemUpload",
    [string]$ToolDirectory = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonwPath = "$env:LOCALAPPDATA\Programs\Python\Python311\pythonw.exe"
)

$ErrorActionPreference = "Stop"
$toolRoot = (Resolve-Path -LiteralPath $ToolDirectory).Path
$worker = Join-Path $toolRoot "orn_item_image_sync.py"
if (-not (Test-Path -LiteralPath $worker -PathType Leaf)) {
    throw "Upload worker not found: $worker"
}
if (-not (Test-Path -LiteralPath $PythonwPath -PathType Leaf)) {
    $resolvedPythonw = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if (-not $resolvedPythonw) {
        throw "pythonw.exe not found. Supply -PythonwPath."
    }
    $PythonwPath = $resolvedPythonw.Source
}

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction `
    -Execute $PythonwPath `
    -Argument ('"' + $worker + '" --drain-queue') `
    -WorkingDirectory $toolRoot
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$repeatTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal `
    -UserId $identity `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -Hidden `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger @($logonTrigger, $repeatTrigger) `
    -Principal $principal `
    -Settings $settings `
    -Description "Publishes approved catalogue JPG files to Ornate NX Server2k22 image folders." `
    -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State, Principal
