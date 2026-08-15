$ErrorActionPreference = "Stop"
$root = "C:\Users\kaila\Desktop\JewelleryCatalogTool"
& python (Join-Path $root "tools\azure_flux2_guarded.py") --dashboard-only --open-dashboard
if ($LASTEXITCODE -ne 0) { throw "Could not generate cost dashboard" }
