[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$secret = Read-Host 'Paste AIS document bridge token' -AsSecureString
$plain = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($plain).Trim()
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($plain)
}
if ([string]::IsNullOrWhiteSpace($token)) { throw 'A non-empty bridge token is required.' }

$target = Join-Path $env:LOCALAPPDATA 'Aradhana\Secrets\document_bridge_token.dpapi'
New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
$bytes = [Text.Encoding]::Unicode.GetBytes($token)
try {
    $encrypted = [Security.Cryptography.ProtectedData]::Protect($bytes, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
    [IO.File]::WriteAllBytes($target, $encrypted)
    Write-Host 'Saved encrypted Router bridge credential for this Windows user.' -ForegroundColor Green
} finally {
    [Array]::Clear($bytes, 0, $bytes.Length)
    $token = $null
}
