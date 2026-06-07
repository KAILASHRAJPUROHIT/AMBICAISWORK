param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [string]$ExpectedWatcherPath = "C:\AradhanaAuditor\invoice_inbox",
    [string]$LogDirectory = "logs\production",
    [string]$ServiceScript = "scripts\aradhana_service_control.ps1"
)

$ErrorActionPreference = "Stop"
$failures = 0

function Write-Check {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Detail
    )

    if ($Passed) {
        Write-Host "PASS $Name - $Detail"
    } else {
        Write-Host "FAIL $Name - $Detail"
        $script:failures += 1
    }
}

function Test-PortListening {
    param([int]$Port)

    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -ne $listener) {
        return $true
    }

    $netstatPattern = "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+\d+"
    $netstatListener = netstat -ano -p tcp | Select-String -Pattern $netstatPattern | Select-Object -First 1
    return $null -ne $netstatListener
}

function Invoke-SmokeRequest {
    param(
        [string]$Path,
        [hashtable]$Headers = @{}
    )

    try {
        return Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl$Path" -Headers $Headers -TimeoutSec 10
    } catch {
        if ($_.Exception.Response) {
            return $_.Exception.Response
        }
        throw
    }
}

try {
    $health = Invoke-SmokeRequest -Path "/health"
    $healthJson = $health.Content | ConvertFrom-Json
    Write-Check "Backend health" ($health.StatusCode -eq 200 -and $healthJson.status -eq "healthy") "GET /health returned status=$($healthJson.status)"
} catch {
    Write-Check "Backend health" $false $_.Exception.Message
}

Write-Check "Backend port $BackendPort" (Test-PortListening $BackendPort) "port $BackendPort listening"
Write-Check "Frontend port $FrontendPort" (Test-PortListening $FrontendPort) "port $FrontendPort listening"

$headers = @{}
if ($env:SMOKE_TEST_SESSION_TOKEN) {
    $headers["X-Session-Token"] = $env:SMOKE_TEST_SESSION_TOKEN
}

try {
    $recon = Invoke-SmokeRequest -Path "/api/reconciliation/open" -Headers $headers
    if ($recon.StatusCode -eq 401) {
        Write-Check "Reconciliation endpoint" $true "reachable and auth-protected with 401"
    } else {
        Write-Check "Reconciliation endpoint" ($recon.StatusCode -ne 500) "status=$($recon.StatusCode)"
    }
} catch {
    Write-Check "Reconciliation endpoint" $false $_.Exception.Message
}

try {
    $ingestion = Invoke-SmokeRequest -Path "/api/admin/ingestion-status" -Headers $headers
    if ($ingestion.StatusCode -eq 401) {
        Write-Check "Ingestion status auth" $true "reachable and auth-protected with 401; set SMOKE_TEST_SESSION_TOKEN for field validation"
    } else {
        $status = $ingestion.Content | ConvertFrom-Json
        $watcherPathMatches = $status.watcher_path -eq $ExpectedWatcherPath
        $localInboxExists = Test-Path $status.local_inbox_path
        $syncHealthy = [bool]$status.sync_running -or ($null -ne $status.last_sync_error -and "$($status.last_sync_error)".Length -gt 0)
        $hasLocalPdfs = [int]$status.local_pdf_count -gt 0

        Write-Check "Ingestion watcher_path" $watcherPathMatches "watcher_path=$($status.watcher_path)"
        Write-Check "Ingestion local inbox exists" $localInboxExists "local_inbox_path=$($status.local_inbox_path)"
        Write-Check "Ingestion sync status" $syncHealthy "sync_running=$($status.sync_running), last_sync_error=$($status.last_sync_error)"
        Write-Check "Ingestion local_pdf_count" $hasLocalPdfs "local_pdf_count=$($status.local_pdf_count)"
    }
} catch {
    Write-Check "Ingestion status" $false $_.Exception.Message
}

try {
    $resolvedLogDirectory = Resolve-Path $LogDirectory -ErrorAction SilentlyContinue
    if ($resolvedLogDirectory) {
        $tracebackMatches = Select-String -Path (Join-Path $resolvedLogDirectory "*.log") `
            -Pattern "BankAlert\.bill_id|SMSAlert\.bill_id" `
            -SimpleMatch:$false `
            -ErrorAction SilentlyContinue
        Write-Check "Removed alert bill_id traceback absent" ($null -eq $tracebackMatches) "searched $resolvedLogDirectory"
    } else {
        Write-Check "Removed alert bill_id traceback absent" $false "log directory not found: $LogDirectory"
    }
} catch {
    Write-Check "Removed alert bill_id traceback absent" $false $_.Exception.Message
}

try {
    $serviceText = Get-Content $ServiceScript -Raw
    $usesExplicitPython = $serviceText -match 'Python311\\python\.exe'
    $usesPyLauncherForBackend = $serviceText -match '(?m)^\s*\$PythonExe\s*=\s*"(py|py\.exe|python)"'
    Write-Check "No py launcher dependency" ($usesExplicitPython -and -not $usesPyLauncherForBackend) "service script uses explicit Python executable"
} catch {
    Write-Check "No py launcher dependency" $false $_.Exception.Message
}

if ($failures -gt 0) {
    Write-Host "SMOKE TEST FAILED: $failures check(s) failed."
    exit 1
}

Write-Host "SMOKE TEST PASSED"
exit 0
