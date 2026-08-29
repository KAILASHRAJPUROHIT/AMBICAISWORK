$ErrorActionPreference = 'Stop'
$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne 'production-long-items-2026-08-29') { exit 0 }

# SHA-256 of the owner-provided production edit password. Plaintext is never
# committed. Prompting works in an interactive production shell; unattended
# agents cannot commit directly to the protected checkpoint.
$expected = 'CE7D2D214993D01FEC803698570051D7C9FB782679AB6AE1A4B0FF9DE1AC66CE'
if (-not [Environment]::UserInteractive) {
    throw 'Production branch is protected. Create a codex/* branch for work.'
}
$secure = Read-Host 'Production edit password' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $actual = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($plain)))
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}
if ($actual -ne $expected) {
    throw 'Production branch commit denied: password verification failed.'
}
