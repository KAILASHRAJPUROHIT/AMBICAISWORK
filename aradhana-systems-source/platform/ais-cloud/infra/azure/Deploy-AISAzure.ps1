[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$SubscriptionId,
    [Parameter(Mandatory)] [string]$ResourceGroup,
    [Parameter(Mandatory)] [string]$ParametersFile,
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$template = Join-Path $PSScriptRoot 'main.bicep'
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw 'Azure CLI is required. Install it from Microsoft, sign in, then rerun this command.'
}
foreach ($path in @($template, $ParametersFile)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing required file: $path" }
}
if ((Get-Content -Raw -LiteralPath $ParametersFile) -match 'REPLACE_') {
    throw 'Parameters file still contains placeholder values. Create a private parameters file outside source control.'
}

& az account set --subscription $SubscriptionId
if ($LASTEXITCODE -ne 0) { throw 'Could not select the Azure subscription.' }

$whatIfArgs = @('deployment','group','what-if','--resource-group',$ResourceGroup,'--template-file',$template,'--parameters',"@$ParametersFile")
& az @whatIfArgs
if ($LASTEXITCODE -ne 0) { throw 'Azure what-if failed. No resources were created.' }
if (-not $Apply) {
    Write-Host 'What-if complete. Review it. Re-run with -Apply only after approval.' -ForegroundColor Yellow
    exit 0
}

& az deployment group create --resource-group $ResourceGroup --template-file $template --parameters "@$ParametersFile"
if ($LASTEXITCODE -ne 0) { throw 'Azure deployment failed. Review the deployment operation logs.' }
Write-Host 'AIS Azure foundation deployed. Configure the custom domain and PostgreSQL private-network phase next.' -ForegroundColor Green
