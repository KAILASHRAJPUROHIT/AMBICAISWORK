param(
    [switch]$InstallFromClipboard,
    [string]$InstallCommandFile
)

$ErrorActionPreference = "Stop"
$toolRoot = Split-Path -Parent $PSScriptRoot
$cloudflared = Join-Path $PSScriptRoot "cloudflared.exe"
$secretDir = Join-Path $toolRoot "config"
$secretPath = Join-Path $secretDir "cloudflare_tunnel_token.dpapi"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$runName = "AradhanaCloudflareTunnel"

if (-not (Test-Path -LiteralPath $cloudflared)) {
    throw "Missing cloudflared.exe at $cloudflared"
}

if ($InstallFromClipboard -or $InstallCommandFile) {
    if ($InstallCommandFile) {
        $installCommand = Get-Content -LiteralPath $InstallCommandFile -Raw
    }
    else {
        $installCommand = Get-Clipboard -Raw
    }
    if ($installCommand -notmatch '(?i)cloudflared(?:\.exe)?\s+service\s+install\s+([^\s]+)') {
        throw "Clipboard does not contain the Cloudflare tunnel installation command."
    }

    $token = $Matches[1].Trim()
    if ($token.Length -lt 40) {
        throw "Cloudflare tunnel token was not valid."
    }

    New-Item -ItemType Directory -Force -Path $secretDir | Out-Null
    $secureToken = ConvertTo-SecureString $token -AsPlainText -Force
    ConvertFrom-SecureString $secureToken | Set-Content -LiteralPath $secretPath -Encoding ASCII

    if ($InstallCommandFile -and (Test-Path -LiteralPath $InstallCommandFile)) {
        Remove-Item -LiteralPath $InstallCommandFile -Force
    }

    $launchCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`""
    New-ItemProperty -Path $runKey -Name $runName -Value $launchCommand -PropertyType String -Force | Out-Null
}

if (-not (Test-Path -LiteralPath $secretPath)) {
    throw "Cloudflare tunnel credential is not installed."
}

$sameBinary = Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -eq $cloudflared }
if ($sameBinary) {
    exit 0
}

$encryptedToken = (Get-Content -LiteralPath $secretPath -Raw).Trim()
$secureToken = ConvertTo-SecureString $encryptedToken
$credential = [pscredential]::new("tunnel", $secureToken)
$plainToken = $credential.GetNetworkCredential().Password
$tokenFile = Join-Path $env:TEMP ("aradhana-cloudflare-{0}.token" -f ([guid]::NewGuid().ToString("N")))

try {
    Set-Content -LiteralPath $tokenFile -Value $plainToken -Encoding ASCII -NoNewline
    Start-Process -FilePath $cloudflared -ArgumentList @("tunnel", "run", "--token-file", $tokenFile) -WindowStyle Hidden
    Start-Sleep -Seconds 4
}
finally {
    $plainToken = $null
    if (Test-Path -LiteralPath $tokenFile) {
        Remove-Item -LiteralPath $tokenFile -Force
    }
}
