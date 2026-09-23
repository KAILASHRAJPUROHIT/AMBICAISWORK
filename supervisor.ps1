# Aradhana Catalogue Tool - supervisor
# Runs on a schedule (Windows Task Scheduler) and does several jobs at once:
#   1. Boot/logon autostart - the scheduled task's "At log on" trigger means
#      this runs shortly after Windows starts, so the tool comes back after
#      a reboot/power loss without anyone at the keyboard.
#   2. Crash recovery - the task also repeats every few minutes, so if the
#      Flask process dies for any reason, this notices within one check
#      interval and relaunches it automatically.
#   3. Crash-loop detection - if relaunching keeps NOT fixing it (a broken
#      code change, a missing dependency), blindly retrying forever every
#      5 minutes just hides a real problem. After several consecutive
#      failures this stops spamming retries as fast and sends one alert
#      instead of silently looping.
#   4. Remote visibility - since the server is deliberately loopback-only
#      (127.0.0.1), there was no way to know the tool was in trouble without
#      being at the keyboard. This sends a push notification (via ntfy.sh -
#      no account needed) when the server goes down, when it recovers, and
#      when a specific engine (Copilot/Codex/Gemini) needs attention.
#
# HARDWALL UPDATE: this now supervises TWO completely independent processes
# — the main catalogue/generation tool (port 7654) AND the isolated capture
# server (port 7655, capture_server.py). They are checked, logged, and
# relaunched in fully separate code blocks with separate state, specifically
# so a problem in one (a hung engine health check, a crash, a slow deep
# probe) can never delay, skip, or otherwise affect the other's check this
# run. The main tool's block used to `exit 0` as soon as it found itself
# down — that would have silently skipped the capture-server check entirely
# on every run where the main tool was unhealthy, which is exactly backwards
# from the point of separating them. Each block now just skips its OWN
# deeper checks and lets the script continue to the other block.
#
# Safe to run even while the tool is already healthy: launch_tool.vbs's own
# "already running?" check means calling it again when the server is fine
# is a harmless no-op. Same for launch_capture.vbs.

$ErrorActionPreference = 'SilentlyContinue'

$ToolDir     = "C:\AradhanaSystems\projects\catalogue-capture\main"
$LogFile     = Join-Path $ToolDir "logs\supervisor.log"
$StateFile   = Join-Path $ToolDir "data\supervisor_state.json"
$RestartRequest = Join-Path $ToolDir "data\restart_catalogue.request"
$CaptureRestartRequest = Join-Path $ToolDir "data\restart_capture.request"
$LogMax      = 2MB
$FailThreshold = 3   # consecutive down-checks (~3 min at the 1-min poll interval) before alerting

# Controlled reload requested by a non-elevated maintenance session. The
# scheduled task itself runs elevated, so only this catalogue service is
# restarted; capture and print services are never touched here.
if (Test-Path -LiteralPath $RestartRequest) {
    try {
        Restart-Service -Name "AradhanaCatalogueTool" -Force -ErrorAction Stop
        Remove-Item -LiteralPath $RestartRequest -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3
    } catch {
        Add-Content -Path $LogFile -Value ("[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] Requested catalogue restart FAILED: " + $_.Exception.Message)
    }
}

# Capture server runs as its own NSSM service.  A maintenance session is not
# elevated, so it requests this narrowly-scoped reload and leaves the main
# catalogue/generation service completely untouched.
if (Test-Path -LiteralPath $CaptureRestartRequest) {
    try {
        Restart-Service -Name "AradhanaCaptureServer" -Force -ErrorAction Stop
        Remove-Item -LiteralPath $CaptureRestartRequest -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3
    } catch {
        Add-Content -Path $LogFile -Value ("[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] Requested capture restart FAILED: " + $_.Exception.Message)
    }
}

# Set this to your own ntfy.sh topic (install the ntfy app, subscribe to the
# same topic string) to get push notifications on your phone. Topic names on
# ntfy.sh are only as private as they are hard to guess - this one has a
# random suffix baked in; change it if you want a different one.
$NtfyTopic = "aradhana-catalogue-qyjkjpa0sj"

function Write-Log([string]$msg) {
    $line = "[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] " + $msg
    Add-Content -Path $LogFile -Value $line
}

function Send-Notification([string]$title, [string]$body, [string]$priority = "default") {
    try {
        $uri = "https://ntfy.sh/" + $NtfyTopic
        Invoke-RestMethod -Uri $uri -Method Post -Body $body -Headers @{
            "Title"    = $title
            "Priority" = $priority
        } -TimeoutSec 10 | Out-Null
        Write-Log "Notification sent: $title"
    } catch {
        Write-Log ("Notification FAILED (non-fatal): " + $_.Exception.Message)
    }
}

function Load-State {
    if (Test-Path $StateFile) {
        try {
            return Get-Content $StateFile -Raw | ConvertFrom-Json
        } catch {}
    }
    return [PSCustomObject]@{
        consecutiveDown = 0
        downAlertSent   = $false
        engineStates    = @{}
        captureConsecutiveDown = 0
        captureDownAlertSent   = $false
    }
}

function Save-State($state) {
    try {
        $state | ConvertTo-Json -Depth 5 | Set-Content -Path $StateFile
    } catch {}
}

if (Test-Path $LogFile) {
    if ((Get-Item $LogFile).Length -gt $LogMax) {
        $old = $LogFile + ".old"
        if (Test-Path $old) { Remove-Item $old -Force }
        Rename-Item $LogFile $old -Force
    }
}

$state = Load-State
# Older state files won't have the capture-specific fields — backfill so
# ConvertTo-Json/property access below never hits a missing-member error.
if (-not (Get-Member -InputObject $state -Name "captureConsecutiveDown" -MemberType Properties)) {
    $state | Add-Member -NotePropertyName "captureConsecutiveDown" -NotePropertyValue 0
}
if (-not (Get-Member -InputObject $state -Name "captureDownAlertSent" -MemberType Properties)) {
    $state | Add-Member -NotePropertyName "captureDownAlertSent" -NotePropertyValue $false
}

# ════════════════════════════════════════════════════════════════════════
# BLOCK 1 — main catalogue/generation tool (port 7654)
# ════════════════════════════════════════════════════════════════════════

$Port = 7654
$mainHealthy = $false
try {
    $url = "http://127.0.0.1:" + $Port + "/"
    $resp = Invoke-WebRequest -Uri $url -TimeoutSec 5 -UseBasicParsing
    if ($resp.StatusCode -eq 200) { $mainHealthy = $true }
} catch {
    $mainHealthy = $false
}

if (-not $mainHealthy) {
    $state.consecutiveDown += 1
    Write-Log ("Main tool not responding (down-check #" + $state.consecutiveDown + ") - restarting AradhanaCatalogueTool service")
    try {
        Restart-Service -Name "AradhanaCatalogueTool" -Force -ErrorAction Stop
        Write-Log "Main tool service restart triggered."
    } catch {
        Write-Log ("Main tool service restart FAILED: " + $_.Exception.Message)
    }
    if ($state.consecutiveDown -ge $FailThreshold -and -not $state.downAlertSent) {
        Send-Notification "Aradhana Catalogue Tool DOWN" `
            ("Main tool has failed to come back for " + $state.consecutiveDown + "+ checks. Relaunch is not fixing it on its own - needs a look. (Capture tool is unaffected - it runs as a separate process.)") `
            "urgent"
        $state.downAlertSent = $true
    }
} else {
    if ($state.downAlertSent) {
        Send-Notification "Aradhana Catalogue Tool recovered" `
            ("Back up after " + $state.consecutiveDown + " failed check(s).") `
            "default"
    }
    $state.consecutiveDown = 0
    $state.downAlertSent = $false

    # Deep engine health - only notify on a CHANGE of state (healthy->unhealthy),
    # not every check, so this doesn't become noise. Only reached when the
    # main tool itself is up - a slow/hung probe here can no longer affect
    # the capture-server block below either way, since that's a separate
    # script block executed unconditionally regardless of what happens here.
    try {
        $health = Invoke-RestMethod -Uri ("http://127.0.0.1:" + $Port + "/api/health") -TimeoutSec 8
        $prevStates = @{}
        if ($state.engineStates) {
            $state.engineStates.PSObject.Properties | ForEach-Object { $prevStates[$_.Name] = $_.Value }
        }
        $newStates = @{}
        foreach ($engine in $health.checks.PSObject.Properties.Name) {
            $ok = $health.checks.$engine.ok
            $detail = $health.checks.$engine.detail
            $newStates[$engine] = $ok
            $wasOk = $prevStates.ContainsKey($engine) -and $prevStates[$engine]
            $hadPrev = $prevStates.ContainsKey($engine)
            if (-not $ok -and ($wasOk -or -not $hadPrev)) {
                Send-Notification ("Aradhana: " + $engine + " needs attention") $detail "default"
            } elseif ($ok -and $hadPrev -and -not $wasOk) {
                Send-Notification ("Aradhana: " + $engine + " recovered") $detail "low"
            }
        }
        $state.engineStates = $newStates
    } catch {
        Write-Log ("Deep health check skipped: " + $_.Exception.Message)
    }
}

# ════════════════════════════════════════════════════════════════════════
# BLOCK 2 — isolated capture server (port 7660) — fully independent check.
# Runs unconditionally regardless of what BLOCK 1 found, and never uses
# `exit` — that's the entire point of splitting these into separate blocks.
# ════════════════════════════════════════════════════════════════════════

$CapturePort = 7660
$captureHealthy = $false
try {
    $captureProbe = New-Object System.Net.Sockets.TcpClient
    $captureConnect = $captureProbe.BeginConnect("127.0.0.1", $CapturePort, $null, $null)
    if ($captureConnect.AsyncWaitHandle.WaitOne(5000, $false)) {
        $captureProbe.EndConnect($captureConnect)
        $captureHealthy = $captureProbe.Connected
    }
    $captureProbe.Close()
} catch {
    $captureHealthy = $false
}

if (-not $captureHealthy) {
    $state.captureConsecutiveDown += 1
    Write-Log ("Capture server not responding (down-check #" + $state.captureConsecutiveDown + ") - restarting AradhanaCaptureServer service")
    try {
        Restart-Service -Name "AradhanaCaptureServer" -Force -ErrorAction Stop
        Write-Log "Capture server service restart triggered."
    } catch {
        Write-Log ("Capture server service restart FAILED: " + $_.Exception.Message)
        Start-Process -FilePath "cscript.exe" `
            -ArgumentList "//nologo", (Join-Path $ScriptDir "launch_capture.vbs") `
            -WindowStyle Hidden
        Write-Log "Capture server standalone launcher fallback triggered."
    }
    if ($state.captureConsecutiveDown -ge $FailThreshold -and -not $state.captureDownAlertSent) {
        Send-Notification "Aradhana CAPTURE SERVER DOWN" `
            ("Capture server has failed to come back for " + $state.captureConsecutiveDown + "+ checks - phones on the shop floor cannot capture right now. Needs a look.") `
            "urgent"
        $state.captureDownAlertSent = $true
    }
} else {
    if ($state.captureDownAlertSent) {
        Send-Notification "Aradhana Capture Server recovered" `
            ("Back up after " + $state.captureConsecutiveDown + " failed check(s).") `
            "default"
    }
    $state.captureConsecutiveDown = 0
    $state.captureDownAlertSent = $false
}

Save-State $state
