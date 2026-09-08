param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("start-prod", "stop-prod", "status-prod", "start-dev", "stop-dev", "restart-prod", "restart-dev")]
    [string]$Mode
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$BundledPython = Join-Path $Root "runtime\python\python.exe"
$PythonExe = if ($env:ARADHANA_PYTHON_EXE -and (Test-Path $env:ARADHANA_PYTHON_EXE)) {
    $env:ARADHANA_PYTHON_EXE
} elseif (Test-Path $BundledPython) {
    $BundledPython
} else {
    "C:\Users\kaila\AppData\Local\Programs\Python\Python311\python.exe"
}
$PythonArgsPrefix = @("-m", "uvicorn", "backend.review_api:app", "--host", "0.0.0.0")
$BundledNode = Join-Path $Root "runtime\node\node.exe"
$NodeExe = if (Test-Path $BundledNode) { $BundledNode } else { (Get-Command "node.exe" -ErrorAction Stop).Source }

function Ensure-Directory($Path) {
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Write-StartupLog($LogDirectory, $Message) {
    Ensure-Directory $LogDirectory
    $logPath = Join-Path $LogDirectory "startup_verification.log"
    if (-not (Test-Path $logPath)) {
        New-Item -ItemType File -Path $logPath | Out-Null
    }
    $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $line = "[$timestamp] $Message"
    Add-Content -Encoding UTF8 -Path $logPath -Value $line
    Write-Host $line
}

function Get-ListenerPid($Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) {
        return [int]$listener.OwningProcess
    }

    $netstatLine = netstat -ano -p tcp |
        Select-String -Pattern "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$" |
        Select-Object -First 1
    if ($netstatLine -and $netstatLine.Matches[0].Groups.Count -gt 1) {
        return [int]$netstatLine.Matches[0].Groups[1].Value
    }

    return $null
}

function Read-PidFile($Path) {
    if (-not (Test-Path $Path)) {
        return $null
    }

    $value = (Get-Content $Path -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if ($value -match '^\d+$') {
        return [int]$value
    }
    return $null
}

function Test-AradhanaHealth($Port) {
    Write-Host "  - Checking health of process on port $Port..."
    try {
        # Check /health endpoint
        $healthUri = "http://127.0.0.1:$Port/health"
        Write-Host "    - GET $healthUri (Timeout: 10s)"
        $healthResponse = Invoke-WebRequest -Uri $healthUri -UseBasicParsing -TimeoutSec 10
        Write-Host "      - Health Status Code: $($healthResponse.StatusCode)"
        Write-Host "      - Health Body: $($healthResponse.Content.Trim())"

        if ($healthResponse.StatusCode -ne 200) {
            Write-Host "  - Decision: Abort (Health endpoint status was not 200)"
            return $false
        }

        $healthInfo = $healthResponse.Content | ConvertFrom-Json -ErrorAction SilentlyContinue
        if (-not ($healthInfo.status -eq "healthy")) {
            Write-Host "  - Decision: Abort (Health JSON status was not 'healthy')"
            return $false
        }
        Write-Host "      - Health JSON Status: Verified 'healthy'"

        # Check /api/version endpoint
        $versionUri = "http://127.0.0.1:$Port/api/version"
        Write-Host "    - GET $versionUri (Timeout: 10s)"
        $versionResponse = Invoke-WebRequest -Uri $versionUri -UseBasicParsing -TimeoutSec 10
        Write-Host "      - Version Status Code: $($versionResponse.StatusCode)"
        Write-Host "      - Version Body: $($versionResponse.Content.Trim())"
        
        if ($versionResponse.StatusCode -ne 200) {
            Write-Host "  - Decision: Abort (Version endpoint status was not 200)"
            return $false
        }
        
        $versionInfo = $versionResponse.Content | ConvertFrom-Json -ErrorAction SilentlyContinue
        if (-not $versionInfo) {
            Write-Host "  - Decision: Abort (Failed to parse version JSON)"
            return $false
        }
        
        if (-not [string]::IsNullOrEmpty($versionInfo.environment)) {
            Write-Host "      - Environment: $($versionInfo.environment)"
            Write-Host "  - Decision: Adopt (Healthy Aradhana backend detected)"
            return $true
        }
        
        Write-Host "  - Decision: Abort (Environment identifier is missing from version JSON)"
        return $false
    }
    catch {
        Write-Host "    - ERROR: An exception occurred during health check: $($_.Exception.Message)"
        Write-Host "  - Decision: Abort (Exception during health check)"
        return $false
    }
}

function Test-AradhanaFrontendHealth($Port) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:$Port" -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -eq 200 -and ($response.Content -match "<title>Aradhana Payment Auditor</title>" -or $response.Content -match '<meta name="application-name" content="Aradhana Payment Auditor">')) {
            return $true
        }
    }
    catch { }
    return $false
}

function Test-ManagedListener($Port, $PidPath, $IsBackend) {
    $listenerPid = Get-ListenerPid $Port
    if (-not $listenerPid) {
        if (Test-Path $PidPath) {
            Remove-Item $PidPath -Force
        }
        return $false # Not running, port is free
    }

    # Port is occupied. Check if it is our managed process.
    $managedPid = Read-PidFile $PidPath
    if ($managedPid -and $managedPid -eq $listenerPid) {
        # A listening port alone is not healthy. The watchdog must repair a
        # stuck API or Vite process rather than adopting it forever.
        $healthy = if ($IsBackend) { Test-AradhanaHealth $Port } else { Test-AradhanaFrontendHealth $Port }
        if ($healthy) { return $true }
        Write-StartupLog (Split-Path $PidPath -Parent) "Managed listener on port $Port is unhealthy; restarting it."
        Stop-Process -Id $listenerPid -Force -ErrorAction SilentlyContinue
        Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
        return $false
    }

    # Port is occupied by an unmanaged process. Check if it's a healthy Aradhana instance.
    if ($IsBackend) {
        if (Test-AradhanaHealth $Port) {
            Write-Host "Found healthy unmanaged Aradhana backend on port $Port (PID $listenerPid). Adopting it."
            Set-Content -Encoding ASCII -Path $PidPath -Value $listenerPid
            return $true # Treat as "already running"
        }
    }
    else {
        if (Test-AradhanaFrontendHealth $Port) {
            Write-Host "Found healthy unmanaged Aradhana frontend on port $Port (PID $listenerPid). Adopting it."
            Set-Content -Encoding ASCII -Path $PidPath -Value $listenerPid
            return $true # Treat as "already running"
        }
    }

    # If we get here, the port is owned by an unmanaged and unhealthy/unknown process.
    throw "Port $Port is already owned by unmanaged and unhealthy/unknown PID $listenerPid. Aborting."
}

function Wait-ForListener($Port, $TimeoutSeconds, $LogDirectory, $Name, $Process = $null) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $nextLogAt = Get-Date
    while ((Get-Date) -lt $deadline) {
        $foundPid = Get-ListenerPid $Port
        if ($foundPid) {
            Write-StartupLog $LogDirectory "$Name listener detected on port $Port (PID $foundPid)."
            return $foundPid
        }
        if ($Process -and $Process.HasExited) {
            Write-StartupLog $LogDirectory "$Name wrapper process exited before port $Port listened. ExitCode=$($Process.ExitCode)."
            return $null
        }
        if ((Get-Date) -ge $nextLogAt) {
            Write-StartupLog $LogDirectory "$Name waiting for port $Port to listen..."
            $nextLogAt = (Get-Date).AddSeconds(5)
        }
        Start-Sleep -Milliseconds 500
    }
    Write-StartupLog $LogDirectory "$Name timed out waiting for port $Port after $TimeoutSeconds seconds."
    return $null
}

function Get-LogTail($Path) {
    if (Test-Path $Path) {
        return ((Get-Content $Path -Tail 20 -ErrorAction SilentlyContinue) -join "`n")
    }
    return ""
}

function Start-ManagedProcess($Name, $Port, $PidPath, $WorkingDirectory, $FilePath, $ArgumentList, $EnvironmentVariables, $LogDirectory, $IsBackend) {
    $alreadyRunning = Test-ManagedListener $Port $PidPath $IsBackend
    if ($alreadyRunning) {
        Write-StartupLog $LogDirectory "$Name already running on port $Port. No duplicate started."
        return
    }

    $outLog = Join-Path $LogDirectory "$Name.out.log"
    $errLog = Join-Path $LogDirectory "$Name.err.log"

    Write-StartupLog $LogDirectory "Starting $Name on port $Port."
    Write-StartupLog $LogDirectory "$Name working directory: $WorkingDirectory"
    Write-StartupLog $LogDirectory "$Name command: $FilePath $($ArgumentList -join ' ')"

    $previousEnvironment = @{}
    foreach ($key in $EnvironmentVariables.Keys) {
        $previousEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
        [Environment]::SetEnvironmentVariable($key, [string]$EnvironmentVariables[$key], "Process")
    }

    try {
        $process = Start-Process -FilePath $FilePath `
            -ArgumentList $ArgumentList `
            -WorkingDirectory $WorkingDirectory `
            -WindowStyle Hidden `
            -RedirectStandardOutput $outLog `
            -RedirectStandardError $errLog `
            -PassThru
    }
    finally {
        foreach ($key in $EnvironmentVariables.Keys) {
            [Environment]::SetEnvironmentVariable($key, $previousEnvironment[$key], "Process")
        }
    }

    Write-StartupLog $LogDirectory "$Name wrapper PID: $($process.Id)."
    $timeoutSeconds = 60
    if (-not $IsBackend) {
        $timeoutSeconds = 90
    }
    $listenerPid = Wait-ForListener $Port $timeoutSeconds $LogDirectory $Name $process
    if (-not $listenerPid) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
        $errTail = Get-LogTail $errLog
        $outTail = Get-LogTail $outLog
        Write-StartupLog $LogDirectory "$Name stdout tail:`n$outTail"
        Write-StartupLog $LogDirectory "$Name stderr tail:`n$errTail"
        throw "$Name did not start listening on port $Port. Check $errLog."
    }

    Start-Sleep -Seconds 2
    $sustainedPid = Get-ListenerPid $Port
    if (-not $sustainedPid) {
        $errTail = Get-LogTail $errLog
        $outTail = Get-LogTail $outLog
        Write-StartupLog $LogDirectory "$Name listener disappeared after startup detection."
        Write-StartupLog $LogDirectory "$Name stdout tail:`n$outTail"
        Write-StartupLog $LogDirectory "$Name stderr tail:`n$errTail"
        throw "$Name started but did not remain listening on port $Port."
    }

    Set-Content -Encoding ASCII -Path $PidPath -Value $sustainedPid
    Write-StartupLog $LogDirectory "$Name running on port $Port (PID $sustainedPid). Logs: $LogDirectory"
}

function Assert-EnvironmentListening($EnvironmentName, $BackendPort, $FrontendPort, $LogDirectory) {
    $backendPid = Get-ListenerPid $BackendPort
    $frontendPid = Get-ListenerPid $FrontendPort

    Write-StartupLog $LogDirectory "$EnvironmentName final verification: backend port $BackendPort PID=$backendPid; frontend port $FrontendPort PID=$frontendPid."

    if (-not $backendPid) {
        throw "$EnvironmentName backend is not listening on port $BackendPort."
    }
    if (-not $frontendPid) {
        throw "$EnvironmentName frontend is not listening on port $FrontendPort."
    }

    Write-StartupLog $LogDirectory "$EnvironmentName startup verified: ports $BackendPort and $FrontendPort are listening."
}

function Stop-ManagedProcess($Name, $Port, $PidPath) {
    $listenerPid = Get-ListenerPid $Port
    $managedPid = Read-PidFile $PidPath

    if ($listenerPid -and $managedPid -and $listenerPid -eq $managedPid) {
        Write-Host "Stopping $Name on port $Port (PID $listenerPid)..."
        Stop-Process -Id $listenerPid -Force -ErrorAction SilentlyContinue
        Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
        return
    }

    if ($listenerPid) {
        Write-Host "$Name port $Port is owned by unmanaged PID $listenerPid. Not stopping it."
        return
    }

    Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
    Write-Host "$Name is not running on port $Port."
}

function Show-ManagedStatus($Name, $Port, $PidPath, $IsBackend) {
    $listenerPid = Get-ListenerPid $Port
    if (-not $listenerPid) {
        Write-Host "$($Name):".PadRight(25) + "STOPPED on port $Port"
        return
    }

    $managedPid = Read-PidFile $PidPath
    $status = ""
    $health = ""

    if ($listenerPid -eq $managedPid) {
        $status = "RUNNING (Managed)"
    } else {
        $status = "RUNNING (Unmanaged)"
    }

    $isHealthy = $false
    if ($IsBackend) {
        if (Test-AradhanaHealth $Port) { $isHealthy = $true }
    } else {
        if (Test-AradhanaFrontendHealth $Port) { $isHealthy = $true }
    }

    if ($isHealthy) {
        $health = "(Healthy)"
    } else {
        $health = "(UNHEALTHY / UNKNOWN)"
    }

    $pidString = "(PID $listenerPid)"
    Write-Host "$($Name):".PadRight(25) + "$status on port $Port $pidString $health"
}

function Get-LanUrl {
    $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -like "192.168.*" -and $_.PrefixOrigin -ne "WellKnown" } |
        Select-Object -First 1 -ExpandProperty IPAddress

    if ($ip) {
        return "http://$ip`:5173"
    }
    return "http://192.168.x.x:5173"
}

function Start-Environment($EnvironmentName, $BackendPort, $FrontendPort, $LogSubdir, $DevMode) {
    $logDirectory = Join-Path $Root "logs\$LogSubdir"
    Ensure-Directory $logDirectory

    $backendPid = Join-Path $logDirectory "backend.pid"
    $frontendPid = Join-Path $logDirectory "frontend.pid"

    Test-ManagedListener $BackendPort $backendPid $true | Out-Null
    Test-ManagedListener $FrontendPort $frontendPid $false | Out-Null

    $backendEnvVars = @{
        PYTHONPATH = "$Root"
        ARADHANA_ENV = "$EnvironmentName"
    }
    if ($DevMode) {
        $devData = Join-Path $Root "data\dev"
        $devPdfPath = Join-Path $devData "InvoicePDFs"
        Ensure-Directory $devData
        Ensure-Directory $devPdfPath
        $devDb = Join-Path $devData "aradhana_dev_isolated.db"
        $productionDb = Join-Path $Root "aradhana_dev.db"
        if ((-not (Test-Path $devDb)) -and (Test-Path $productionDb)) {
            Copy-Item -Path $productionDb -Destination $devDb
            Write-Host "Seeded isolated development DB at $devDb."
        }
        $backendEnvVars["ARADHANA_DB_PATH"] = "$devDb"
        $backendEnvVars["INVOICE_SHARE_PATH"] = "$devPdfPath"
        $backendEnvVars["INVOICE_PDF_PATH"] = "$devPdfPath"
    }

    $backendArgs = $PythonArgsPrefix + @("--port", "$BackendPort")

    $frontendRoot = Join-Path $Root "frontend"
    $viteEntry = Join-Path $frontendRoot "node_modules\vite\bin\vite.js"
    if (-not (Test-Path $viteEntry)) {
        throw "Vite entrypoint not found at $viteEntry. Run npm install in frontend first."
    }
    $frontendArgs = @($viteEntry, "--host", "0.0.0.0", "--port", "$FrontendPort", "--strictPort")
    $frontendEnvVars = @{
        VITE_DEV_SERVER_PORT = "$FrontendPort"
        VITE_BACKEND_PORT = "$BackendPort"
        ARADHANA_ENV = "$EnvironmentName"
    }

    Start-ManagedProcess "$EnvironmentName-backend" $BackendPort $backendPid $Root $PythonExe $backendArgs $backendEnvVars $logDirectory $true
    Start-ManagedProcess "$EnvironmentName-frontend" $FrontendPort $frontendPid $frontendRoot $NodeExe $frontendArgs $frontendEnvVars $logDirectory $false
    Assert-EnvironmentListening $EnvironmentName $BackendPort $FrontendPort $logDirectory

    if ($EnvironmentName -eq "production") {
        Write-Host "Production client URL: $(Get-LanUrl)"
    } else {
        Write-Host "Development URL: http://127.0.0.1:$FrontendPort"
    }
}

switch ($Mode) {
    "start-prod" {
        Start-Environment "production" 8000 5173 "production" $false
    }
    "stop-prod" {
        $logDirectory = Join-Path $Root "logs\production"
        Stop-ManagedProcess "production-frontend" 5173 (Join-Path $logDirectory "frontend.pid")
        Stop-ManagedProcess "production-backend" 8000 (Join-Path $logDirectory "backend.pid")
    }
    "status-prod" {
        $logDirectory = Join-Path $Root "logs\production"
        Show-ManagedStatus "Production Backend" 8000 (Join-Path $logDirectory "backend.pid") $true
        Show-ManagedStatus "Production Frontend" 5173 (Join-Path $logDirectory "frontend.pid") $false
        Write-Host ""
        Write-Host "Production client URL: $(Get-LanUrl)"
        Write-Host "Production logs: $(Join-Path $Root 'logs\production')"
    }
    "start-dev" {
        Start-Environment "dev" 8010 5183 "dev" $true
    }
    "stop-dev" {
        $logDirectory = Join-Path $Root "logs\dev"
        Stop-ManagedProcess "dev-frontend" 5183 (Join-Path $logDirectory "frontend.pid")
        Stop-ManagedProcess "dev-backend" 8010 (Join-Path $logDirectory "backend.pid")
    }
    "restart-prod" {
        $logDirectory = Join-Path $Root "logs\production"
        Stop-ManagedProcess "production-frontend" 5173 (Join-Path $logDirectory "frontend.pid")
        Stop-ManagedProcess "production-backend" 8000 (Join-Path $logDirectory "backend.pid")
        Start-Sleep -Seconds 2
        Start-Environment "production" 8000 5173 "production" $false
    }
    "restart-dev" {
        $logDirectory = Join-Path $Root "logs\dev"
        Stop-ManagedProcess "dev-frontend" 5183 (Join-Path $logDirectory "frontend.pid")
        Stop-ManagedProcess "dev-backend" 8010 (Join-Path $logDirectory "backend.pid")
        Start-Sleep -Seconds 2
        Start-Environment "dev" 8010 5183 "dev" $true
    }
}
