param([Parameter(Mandatory)] [string] $ReleaseRoot)
$ErrorActionPreference = 'Stop'
Copy-Item (Join-Path $ReleaseRoot 'payload.txt') (Join-Path $env:TEMP 'ais-ota-test-result.txt') -Force
