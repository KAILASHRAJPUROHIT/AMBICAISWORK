$ErrorActionPreference = "Stop"

Restart-Service -Name "AMBICCatalogueTool" -Force
$deadline = (Get-Date).AddSeconds(20)
do {
    Start-Sleep -Milliseconds 500
    $service = Get-Service -Name "AMBICCatalogueTool"
} until ($service.Status -eq "Running" -or (Get-Date) -ge $deadline)

if ($service.Status -ne "Running") {
    throw "AMBICCatalogueTool did not return to Running state."
}
