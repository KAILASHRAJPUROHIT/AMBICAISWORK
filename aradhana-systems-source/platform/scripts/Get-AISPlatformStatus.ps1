[CmdletBinding()]
param(
    [string]$PlatformRoot = 'C:\AradhanaSystems\platform',
    [switch]$IncludeNetworkHealth
)

$ErrorActionPreference = 'Stop'
$registry = Get-Content -Raw -LiteralPath (Join-Path $PlatformRoot 'core\ais.registry.json') | ConvertFrom-Json
$results = foreach ($service in $registry.services) {
    $state = 'declared'
    $detail = ''
    if ($IncludeNetworkHealth) {
        try {
            $response = Invoke-WebRequest -Uri $service.health -UseBasicParsing -TimeoutSec 3
            $state = if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) { 'healthy' } else { "http_$($response.StatusCode)" }
        } catch {
            $state = 'unreachable'
            $detail = $_.Exception.Message
        }
    }
    [pscustomobject]@{ Component = $service.id; Host = $service.host; Port = $service.port; Scope = $service.scope; State = $state; Detail = $detail }
}
$results | Format-Table -AutoSize
