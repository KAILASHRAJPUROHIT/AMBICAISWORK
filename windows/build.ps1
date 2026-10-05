<#
.SYNOPSIS
  Builds the AMBIC Windows components from windows/upstream into windows/dist.

.DESCRIPTION
  - Uses a portable Go toolchain in $ToolsDir\go (downloaded from go.dev and checked against Go's published SHA-256 when missing).
    Nothing is installed into Windows and no admin rights are needed. Delete $ToolsDir\go to remove it.
  - Generates the console's page templates (templ), which upstream does not commit.
  - Cross-checks every module compiles, then writes the Windows executables to windows\dist (git-ignored).

  Outputs: agent.exe, agent-updater.exe, agent-worker.exe, cert-manager.exe, ocsp-responder.exe, console.exe
#>
param(
    [string] $ToolsDir = 'C:\AradhanaSystems\tools',
    [switch] $SkipConsole
)
$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$up = Join-Path $root 'upstream'
$dist = Join-Path $root 'dist'
$goRoot = Join-Path $ToolsDir 'go'
$goExe = Join-Path $goRoot 'bin\go.exe'

if (-not (Test-Path $goExe)) {
    Write-Host 'Downloading Go...'
    $info = (Invoke-RestMethod 'https://go.dev/dl/?mode=json')[0]
    $file = $info.files | Where-Object { $_.os -eq 'windows' -and $_.arch -eq 'amd64' -and $_.kind -eq 'archive' }
    $zip = Join-Path $env:TEMP $file.filename
    Invoke-WebRequest "https://go.dev/dl/$($file.filename)" -OutFile $zip
    if ((Get-FileHash $zip -Algorithm SHA256).Hash.ToLower() -ne $file.sha256) { throw 'Go download failed its checksum; not using it.' }
    New-Item -ItemType Directory -Force $ToolsDir | Out-Null
    Expand-Archive $zip -DestinationPath $ToolsDir -Force
    Remove-Item $zip
}

$env:GOROOT = $goRoot
$env:GOPATH = Join-Path $ToolsDir 'gopath'
$env:GOCACHE = Join-Path $ToolsDir 'gocache'
$env:GOOS = 'windows'
$env:GOARCH = 'amd64'
& $goExe version

New-Item -ItemType Directory -Force $dist | Out-Null

function Build([string] $Repo, [string] $Package, [string] $Name) {
    Push-Location (Join-Path $up $Repo)
    try {
        Write-Host "Building $Name ..."
        & $goExe build -o (Join-Path $dist "$Name.exe") $Package
        if ($LASTEXITCODE -ne 0) { throw "Build of $Name failed." }
    } finally { Pop-Location }
}

Build 'openuem-agent'          './internal/service/windows'               'agent'
Build 'openuem-agent-updater'  './internal/service/windows'               'agent-updater'
Build 'openuem-worker'         './internal/service/agent-worker/windows'  'agent-worker'
Build 'openuem-cert-manager'   '.'                                        'cert-manager'
Build 'openuem-ocsp-responder' '.'                                        'ocsp-responder'

if (-not $SkipConsole) {
    $templ = Join-Path $env:GOPATH 'bin\templ.exe'
    if (-not (Test-Path $templ)) {
        $env:GOOS = ''; $env:GOARCH = ''     # templ runs on this machine
        & $goExe install 'github.com/a-h/templ/cmd/templ@v0.3.1001'
        $env:GOOS = 'windows'; $env:GOARCH = 'amd64'
    }
    Push-Location (Join-Path $up 'openuem-console')
    try { & $templ generate | Out-Null } finally { Pop-Location }
    Build 'openuem-console' '.' 'console'
}

Get-ChildItem $dist -Filter *.exe | Select-Object Name, @{n='MB'; e={[math]::Round($_.Length / 1MB, 1)}}
