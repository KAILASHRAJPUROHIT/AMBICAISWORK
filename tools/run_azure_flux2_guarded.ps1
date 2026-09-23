param(
    [Parameter(Mandatory = $true)][string]$InputImage,
    [string]$OutputImage,
    [string]$PromptFile,
    [string]$BackgroundImage,
    [string]$Category
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Security
$root = "C:\AradhanaSystems\projects\catalogue-capture\main"
$configPath = Join-Path $root "config\azure_flux2_guard.json"
$script = Join-Path $root "tools\azure_flux2_guarded.py"
$python = "C:\Users\kaila\AppData\Local\Programs\Python\Python311\python.exe"
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "Run tools\setup_azure_flux2_secure.ps1 once first."
}
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
if (-not (Test-Path -LiteralPath $config.encrypted_key_file -PathType Leaf)) {
    throw "Encrypted API key is missing. Run secure setup again."
}
if (-not (Test-Path -LiteralPath $InputImage -PathType Leaf)) {
    throw "Input image is missing: $InputImage"
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Catalogue Python runtime is missing: $python"
}
if ([string]::IsNullOrWhiteSpace($OutputImage)) {
    $stem = [IO.Path]::GetFileNameWithoutExtension($InputImage)
    $OutputImage = Join-Path $root "output\${stem}_flux2_pro.png"
}
$hybridOutput = [IO.Path]::Combine([IO.Path]::GetDirectoryName($OutputImage), ([IO.Path]::GetFileNameWithoutExtension($OutputImage) + "_hybrid.png"))
$promptArgs = @()
if (-not [string]::IsNullOrWhiteSpace($PromptFile)) {
    $promptArgs = @("--prompt-file", $PromptFile)
}
$backgroundArgs = @()
if (-not [string]::IsNullOrWhiteSpace($BackgroundImage)) {
    if (-not (Test-Path -LiteralPath $BackgroundImage -PathType Leaf)) {
        throw "Background image is missing: $BackgroundImage"
    }
    $backgroundArgs = @("--background", $BackgroundImage)
}
$categoryArgs = @()
if (-not [string]::IsNullOrWhiteSpace($Category)) {
    $categoryArgs = @("--category", $Category)
}

$protectedKey = [IO.File]::ReadAllBytes($config.encrypted_key_file)
$clearKey = [Security.Cryptography.ProtectedData]::Unprotect(
    $protectedKey,
    $null,
    [Security.Cryptography.DataProtectionScope]::LocalMachine
)
try {
    $plainKey = [Text.Encoding]::UTF8.GetString($clearKey)
    $env:AZURE_ENDPOINT = $config.endpoint
    $env:AZURE_API_KEY = $plainKey
    & $python $script --input $InputImage --output $OutputImage --hybrid-output $hybridOutput @promptArgs @backgroundArgs @categoryArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Guarded FLUX.2-pro call failed. See automatic_retries in the guard ledger for how many attempts were made."
    }
}
finally {
    Remove-Item Env:AZURE_ENDPOINT -ErrorAction SilentlyContinue
    Remove-Item Env:AZURE_API_KEY -ErrorAction SilentlyContinue
    $plainKey = $null
    if ($null -ne $clearKey) {
        [Array]::Clear($clearKey, 0, $clearKey.Length)
    }
}

Write-Host "Pro output: $OutputImage"
Write-Host "Hybrid output: $hybridOutput"
