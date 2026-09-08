[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$entry = Join-Path $root "scripts\portable_bank_activity_notifier.py"
$releaseDir = Join-Path $root "release\bank-activity-notifier"
$buildDir = Join-Path $root ".build\bank-activity-notifier-v$($Version.Replace('.', '_'))"
$name = "AradhanaBankActivityNotifierSetup-v$Version"
$python311 = "C:\Users\kaila\AppData\Local\Programs\Python\Python311\python.exe"
$python = if (Test-Path -LiteralPath $python311) { $python311 } else { "python" }

$source = Get-Content -LiteralPath $entry -Raw
if ($source -notmatch "APP_VERSION = `"$([regex]::Escape($Version))`"") {
    throw "APP_VERSION in $entry must be $Version before building."
}

New-Item -ItemType Directory -Force -Path $releaseDir, $buildDir | Out-Null
& $python -m PyInstaller --noconfirm --clean --onefile --windowed --name $name `
    --distpath $releaseDir --workpath $buildDir --specpath $buildDir `
    --add-data "$root\scripts;scripts" $entry
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

$exe = Join-Path $releaseDir "$name.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "Expected EXE was not built: $exe" }
$hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
$manifest = [ordered]@{
    version = $Version
    filename = [IO.Path]::GetFileName($exe)
    sha256 = $hash
    published_at = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json
Set-Content -LiteralPath (Join-Path $releaseDir "current.json") -Value $manifest -Encoding UTF8
Write-Host "Published notifier $Version"
Write-Host "Manifest: $(Join-Path $releaseDir 'current.json')"
