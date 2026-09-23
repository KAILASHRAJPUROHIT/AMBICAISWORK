$ErrorActionPreference = "Stop"

$catalogueRoot = $PSScriptRoot
Set-Location -LiteralPath $catalogueRoot
$env:ARADHANA_ENGINE = "azure_flux2_pro"

$azureConfig = Join-Path $catalogueRoot "config\azure_flux2_guard.json"
$azureKey = Join-Path $catalogueRoot "config\azure_flux2_pro_key.dpapi"
$portFile = Join-Path $catalogueRoot "port.txt"
$port = 7654

if (-not (Test-Path -LiteralPath $azureConfig -PathType Leaf)) {
    throw "Azure FLUX.2 Pro guard config missing: $azureConfig"
}
if (-not (Test-Path -LiteralPath $azureKey -PathType Leaf)) {
    throw "Encrypted Azure API key missing: $azureKey"
}

$pythonCommand = Get-Command python.exe -ErrorAction Stop
$appExecutable = $pythonCommand.Source
$appArgs = @("app.py")

$alreadyReady = $false
try {
    $existing = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/health" -UseBasicParsing -TimeoutSec 2
    $alreadyReady = $existing.StatusCode -eq 200
} catch {}

if (-not $alreadyReady) {
    Start-Process -FilePath $appExecutable -ArgumentList $appArgs -WorkingDirectory $catalogueRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $catalogueRoot "logs\catalogue_app.out.log") -RedirectStandardError (Join-Path $catalogueRoot "logs\catalogue_app.err.log")
}

$deadline = (Get-Date).AddSeconds(45)
$ready = $false
while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/login" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Milliseconds 500
}

if (-not $ready) {
    throw "Catalogue V2 did not become ready. See logs\catalogue_app.err.log."
}

$url = "http://127.0.0.1:$port"
$lanUrl = "http://aradhana:$port"
try {
    Start-Process -FilePath "explorer.exe" -ArgumentList $url -ErrorAction Stop
} catch {
    Write-Warning "Browser could not be opened automatically. Copy the URL below."
}
Write-Host "Catalogue V2 ready: $url"
Write-Host "Permanent LAN URL: $lanUrl"
Write-Host "Engine: Azure FLUX.2 Pro only. Password required for every batch."
