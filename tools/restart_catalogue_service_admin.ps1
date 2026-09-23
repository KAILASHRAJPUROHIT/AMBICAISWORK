$ErrorActionPreference = "Stop"

Restart-Service -Name "AradhanaCatalogueTool" -Force
$deadline = (Get-Date).AddSeconds(20)
do {
    Start-Sleep -Milliseconds 500
    $service = Get-Service -Name "AradhanaCatalogueTool"
} until ($service.Status -eq "Running" -or (Get-Date) -ge $deadline)

if ($service.Status -ne "Running") {
    throw "AradhanaCatalogueTool did not return to Running state."
}
