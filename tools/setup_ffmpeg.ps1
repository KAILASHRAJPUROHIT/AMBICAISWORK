$ErrorActionPreference = "Stop"

$root = "C:\AradhanaSystems\projects\catalogue-capture\main"
$destDir = Join-Path $root "tools\ffmpeg"

$existing = Get-ChildItem -Path $destDir -Recurse -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "ffmpeg already installed at $($existing[0].FullName)"
    exit 0
}

New-Item -ItemType Directory -Force -Path $destDir | Out-Null
$zipPath = Join-Path $env:TEMP "ffmpeg_setup.zip"
Write-Host "Downloading ffmpeg (essentials build)..."
Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $zipPath -UseBasicParsing
Expand-Archive -Path $zipPath -DestinationPath $destDir -Force
Remove-Item $zipPath -Force

$installed = Get-ChildItem -Path $destDir -Recurse -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue
if (-not $installed) {
    throw "ffmpeg.exe not found after extraction -- the download or archive layout may have changed."
}
Write-Host "ffmpeg installed at $($installed[0].FullName)"
