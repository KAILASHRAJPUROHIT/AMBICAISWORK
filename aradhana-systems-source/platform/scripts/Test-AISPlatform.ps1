[CmdletBinding()]
param(
    [string]$PlatformRoot = 'C:\AradhanaSystems\platform'
)

$ErrorActionPreference = 'Stop'
$registryPath = Join-Path $PlatformRoot 'core\ais.registry.json'
$devicesPath = Join-Path $PlatformRoot 'core\ais.devices.json'
foreach ($path in @($registryPath, $devicesPath, (Join-Path $PlatformRoot 'core\ais.registry.schema.json'), (Join-Path $PlatformRoot 'core\ais.devices.schema.json'), (Join-Path $PlatformRoot 'core\plugin.manifest.schema.json'))) {
    if (-not (Test-Path -LiteralPath $path)) { throw "AIS required file missing: $path" }
}

$registry = Get-Content -Raw -LiteralPath $registryPath | ConvertFrom-Json
$devices = Get-Content -Raw -LiteralPath $devicesPath | ConvertFrom-Json
$deviceIds = @($devices.devices.id)
$failures = [System.Collections.Generic.List[string]]::new()
$targets = @($registry.projects.ota_target) + @($registry.plugins.ota_target)
if ((@($targets | Group-Object | Where-Object Count -gt 1)).Count) { $failures.Add('Every AIS OTA target must be globally unique.') }

foreach ($project in $registry.projects) {
    if (-not (Test-Path -LiteralPath $project.path)) { $failures.Add("Project path missing: $($project.id) -> $($project.path)") }
    if ($deviceIds -notcontains $project.owner_device) { $failures.Add("Project owner unknown: $($project.id) -> $($project.owner_device)") }
    if ($project.ota_target -notmatch '^[A-Za-z0-9_-]+$') { $failures.Add("Invalid OTA target: $($project.id)") }
}
foreach ($plugin in $registry.plugins) {
    if (-not (Test-Path -LiteralPath $plugin.path)) { $failures.Add("Plugin path missing: $($plugin.id) -> $($plugin.path)"); continue }
    $manifest = Join-Path $plugin.path 'ais.plugin.json'
    if (-not (Test-Path -LiteralPath $manifest)) { $failures.Add("Plugin manifest missing: $($plugin.id)"); continue }
    try { $content = Get-Content -Raw -LiteralPath $manifest | ConvertFrom-Json } catch { $failures.Add("Plugin manifest invalid JSON: $($plugin.id)"); continue }
    if ($content.id -ne $plugin.id) { $failures.Add("Plugin id mismatch: registry=$($plugin.id), manifest=$($content.id)") }
    if ($content.ota.target -ne $plugin.ota_target) { $failures.Add("Plugin OTA target mismatch: $($plugin.id)") }
}
foreach ($service in $registry.services) {
    if ($deviceIds -notcontains $service.host) { $failures.Add("Service host unknown: $($service.id) -> $($service.host)") }
    if ($service.port -lt 1 -or $service.port -gt 65535) { $failures.Add("Invalid service port: $($service.id)") }
}
if ($failures.Count) { $failures | ForEach-Object { Write-Error $_ }; throw "AIS platform validation failed ($($failures.Count) issue(s))." }

[pscustomobject]@{
    Status = 'valid'
    Projects = @($registry.projects).Count
    Plugins = @($registry.plugins).Count
    Devices = @($devices.devices).Count
    CheckedAt = (Get-Date).ToUniversalTime().ToString('o')
}
