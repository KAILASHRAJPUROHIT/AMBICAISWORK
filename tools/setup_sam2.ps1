$ErrorActionPreference = "Stop"

$root = "C:\AradhanaSystems\projects\catalogue-capture\main"
$destDir = Join-Path $root "models\sam2"
$destFile = Join-Path $destDir "sam2.1_hiera_large.pt"

if (Test-Path $destFile) {
    Write-Host "SAM2.1 Hiera Large checkpoint already present at $destFile"
    exit 0
}

New-Item -ItemType Directory -Force -Path $destDir | Out-Null
Write-Host "Downloading SAM2.1 Hiera Large checkpoint (~900MB, Meta's official public release)..."
Invoke-WebRequest -Uri "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt" -OutFile $destFile -UseBasicParsing

if (-not (Test-Path $destFile)) {
    throw "Checkpoint not found after download."
}
Write-Host "SAM2.1 Hiera Large checkpoint installed at $destFile"
Write-Host "Grounding DINO needs no manual setup -- its weights download automatically on first use via HuggingFace Hub."
