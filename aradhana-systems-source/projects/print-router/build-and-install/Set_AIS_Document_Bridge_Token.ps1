$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security

$secretDirectory = Join-Path $env:LOCALAPPDATA 'Aradhana\Secrets'
$secretPath = Join-Path $secretDirectory 'document_bridge_token.dpapi'
$secureToken = Read-Host 'Paste AIS document bridge token' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)

try {
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    if ([string]::IsNullOrWhiteSpace($plainToken)) {
        throw 'No token was supplied.'
    }

    $plainBytes = [Text.Encoding]::Unicode.GetBytes($plainToken)
    $encryptedBytes = [System.Security.Cryptography.ProtectedData]::Protect(
        $plainBytes,
        $null,
        [System.Security.Cryptography.DataProtectionScope]::CurrentUser
    )

    [IO.Directory]::CreateDirectory($secretDirectory) | Out-Null
    [IO.File]::WriteAllBytes($secretPath, $encryptedBytes)
    [Array]::Clear($plainBytes, 0, $plainBytes.Length)
    Write-Host 'Saved encrypted Router bridge credential for this Windows user.' -ForegroundColor Green
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
