$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Security

$root = "C:\AradhanaSystems\projects\catalogue-capture\main"
$configDir = Join-Path $root "config"
$configPath = Join-Path $configDir "azure_flux2_guard.json"
$keyPath = Join-Path $configDir "azure_flux2_pro_key.dpapi"
$defaultEndpoint = "https://kuldeeprajpurohit309-07-resource.services.ai.azure.com"

New-Item -ItemType Directory -Path $configDir -Force | Out-Null
$enteredEndpoint = Read-Host "Foundry endpoint [$defaultEndpoint]"
$endpoint = if ([string]::IsNullOrWhiteSpace($enteredEndpoint)) { $defaultEndpoint } else { $enteredEndpoint.Trim().TrimEnd("/") }
if ($endpoint -notmatch '^https://.+\.services\.ai\.azure\.com$') {
    throw "Unexpected endpoint. It must end in .services.ai.azure.com"
}

$secureKey = Read-Host "Paste the Foundry API key once; Windows encrypts it for this computer" -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    $clearKey = [Text.Encoding]::UTF8.GetBytes($plainKey)
    $protectedKey = [Security.Cryptography.ProtectedData]::Protect(
        $clearKey,
        $null,
        [Security.Cryptography.DataProtectionScope]::LocalMachine
    )
    [IO.File]::WriteAllBytes($keyPath, $protectedKey)
}
finally {
    $plainKey = $null
    if ($null -ne $clearKey) { [Array]::Clear($clearKey, 0, $clearKey.Length) }
    if ($keyPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer) }
}
$principal = "$env:USERDOMAIN\$env:USERNAME"
& icacls.exe $keyPath /inheritance:r /grant:r "${principal}:(F)" "SYSTEM:(R)" | Out-Null

$config = [ordered]@{
    schema = 1
    endpoint = $endpoint
    encrypted_key_file = $keyPath
    model = "FLUX.2-pro"
    output_width = 1152
    output_height = 864
    final_width = 2048
    final_height = 1536
    maximum_reference_megapixels = 4.0
    default_prompt_file = (Join-Path $configDir "flux2_pro_catalogue_prompt.txt")
    lifetime_hard_cap_usd = 5.00
    daily_hard_cap_usd = 0.50
    maximum_calls_per_day = 4
    cost_safety_factor = 1.25
    trial_credit_start_usd = 200.00
    historical_estimated_spend_usd = 1.22
    automatic_retries = 0
    credential_protection = "Windows DPAPI LocalMachine; ACL limited to setup user and SYSTEM"
}
$config | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $configPath -Encoding UTF8

Write-Host "SECURE SETUP COMPLETE"
Write-Host "Endpoint config: $configPath"
Write-Host "Encrypted key: $keyPath"
Write-Host "Hard caps: `$5.00 lifetime, `$0.50/day, 4 calls/day, zero retries, 4 MP reference cap"
