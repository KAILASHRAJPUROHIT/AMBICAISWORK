<#
  Install the sales-leaderboard collector on the shop server (SERVER2K22).

  Run ONCE in an elevated PowerShell on the Dell:
      powershell -ExecutionPolicy Bypass -File "<path>\install-collector.ps1"

  What it does
    1. Rotates the SQL login password (new random password generated HERE, never displayed
       or logged) and stores it in the machine environment.
    2. Sets the machine environment the collector reads.
    3. Runs the collector once to prove SQL -> MDM works.
    4. Registers a background task (runs at startup as SYSTEM, restarts itself if it dies).
    5. Deletes any staged copy of this script that carries the push token.

  The push token comes from -Token, or is asked for. A staged copy prepared by the deployer has it
  filled in below and removes itself when finished.
#>
param(
    [string]$Token = '__COLLECTOR_TOKEN__'
)

# 'Continue': Windows PowerShell 5.1 turns anything a native program prints on stderr (Python logging,
# pip) into a terminating error under 'Stop'. Critical cmdlets below use -ErrorAction Stop explicitly.
$ErrorActionPreference = 'Continue'
$Endpoint  = 'https://mdm.ambicdigital.in/rest/public/collector/v1/leaderboard'
$SqlLogin  = 'aiswork_leaderboard'
$TaskName  = 'AradhanaLeaderboardCollector'
$InstallTo = 'C:\ProgramData\AradhanaLeaderboard'
$Here      = Split-Path -Parent $MyInvocation.MyCommand.Path

function Step($m) { Write-Host ""; Write-Host "== $m" -ForegroundColor Cyan }
function Fail($m) { Write-Host ""; Write-Host "STOPPED: $m" -ForegroundColor Red; exit 1 }

# --- 0. Preconditions ------------------------------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Fail 'Open PowerShell with "Run as administrator" and run this again.' }

if ($Token -eq '__COLLECTOR_TOKEN__' -or [string]::IsNullOrWhiteSpace($Token)) {
    $sec = Read-Host 'Collector push token' -AsSecureString
    $Token = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
}
if ($Token.Length -lt 16) { Fail 'The push token looks too short.' }

$Collector = Join-Path $Here 'leaderboard_collector.py'
if (-not (Test-Path $Collector)) { Fail "leaderboard_collector.py must sit next to this script ($Here)." }

# --- 1. Python with pyodbc -------------------------------------------------------------------
Step 'Finding Python'
$candidates = @()
foreach ($n in 'python.exe', 'py.exe') {
    $c = Get-Command $n -ErrorAction SilentlyContinue
    if ($c) { $candidates += $c.Source }
}
$candidates += Get-ChildItem 'C:\Python*\python.exe', 'C:\Program Files\Python*\python.exe', 'C:\Users\*\AppData\Local\Programs\Python\Python*\python.exe' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }
$Python = $null
foreach ($c in $candidates) {
    if ($c -like '*\WindowsApps\*') { continue }
    & $c -c 'import pyodbc' 2>$null
    if ($LASTEXITCODE -eq 0) { $Python = $c; break }
}
if (-not $Python) {
    foreach ($c in $candidates) {
        if ($c -like '*\WindowsApps\*') { continue }
        Write-Host "Installing pyodbc for $c ..."
        & $c -m pip install --quiet pyodbc
        & $c -c 'import pyodbc' 2>$null
        if ($LASTEXITCODE -eq 0) { $Python = $c; break }
    }
}
if (-not $Python) { Fail 'No Python with pyodbc was found and it could not be installed. Tell Claude what "where python" prints.' }
$PythonW = Join-Path (Split-Path $Python -Parent) 'pythonw.exe'
if (-not (Test-Path $PythonW)) { $PythonW = $Python }
Write-Host "Using $Python"

# --- 2. Install the collector ----------------------------------------------------------------
Step 'Installing the collector'
New-Item -ItemType Directory -Force -Path $InstallTo -ErrorAction Stop | Out-Null
Copy-Item $Collector (Join-Path $InstallTo 'leaderboard_collector.py') -Force -ErrorAction Stop
$LogFile = Join-Path $InstallTo 'collector.log'

# --- 3. Rotate the SQL password (generated here, never shown) --------------------------------
Step 'Rotating the SQL login password'
$SqlServer = [Environment]::GetEnvironmentVariable('ORNATE_SQL_SERVER', 'Machine')
if ([string]::IsNullOrWhiteSpace($SqlServer)) { $SqlServer = "$env:COMPUTERNAME\EXP2022" }

$alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'.ToCharArray()
$rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
$bytes = New-Object byte[] 40
$rng.GetBytes($bytes)
$NewPassword = -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
# guarantee upper + lower + digit so SQL Server's complexity policy is always satisfied
$NewPassword = 'Lb' + '7' + $NewPassword

$rotate = @'
import os, sys, pyodbc
server, login, pwd = os.environ["ROT_SERVER"], os.environ["ROT_LOGIN"], os.environ["ROT_PWD"]
sa_pwd = os.environ.get("ROT_SA_PWD", "")
if sa_pwd:
    auth = "UID=sa;PWD=" + sa_pwd
else:
    auth = "Trusted_Connection=yes"
cs = "DRIVER={ODBC Driver 17 for SQL Server};SERVER=" + server + ";" + auth + ";Encrypt=no;TrustServerCertificate=yes;Connection Timeout=15"
conn = pyodbc.connect(cs, autocommit=True)
conn.execute("ALTER LOGIN [" + login + "] WITH PASSWORD = N'" + pwd + "'")
print("rotated")
'@
$env:ROT_SERVER = $SqlServer; $env:ROT_LOGIN = $SqlLogin; $env:ROT_PWD = $NewPassword
$out = $rotate | & $Python - 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Windows sign-in could not change the login. Enter the SQL "sa" password to do it that way.' -ForegroundColor Yellow
    $sa = Read-Host 'SQL sa password' -AsSecureString
    $env:ROT_SA_PWD = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sa))
    $out = $rotate | & $Python - 2>&1
    Remove-Item Env:\ROT_SA_PWD -ErrorAction SilentlyContinue
}
Remove-Item Env:\ROT_SERVER, Env:\ROT_LOGIN, Env:\ROT_PWD -ErrorAction SilentlyContinue
if ($LASTEXITCODE -ne 0 -or (($out | Out-String) -notmatch 'rotated')) {
    Fail ("Could not change the SQL password. Details (no secrets): " + (($out | Out-String) -replace [regex]::Escape($NewPassword), '***'))
}
Write-Host 'SQL password rotated. The old (leaked) password no longer works.'

# --- 4. Machine environment ------------------------------------------------------------------
Step 'Saving settings (machine environment)'
$vars = [ordered]@{
    ORNATE_SQL_SERVER            = $SqlServer
    ORNATE_SQL_USER              = $SqlLogin
    ORNATE_SQL_PASSWORD          = $NewPassword
    LEADERBOARD_ENDPOINT         = $Endpoint
    LEADERBOARD_TOKEN            = $Token
    LEADERBOARD_INTERVAL_SECONDS = '30'
    LEADERBOARD_LOG_FILE         = $LogFile
}
foreach ($k in $vars.Keys) {
    [Environment]::SetEnvironmentVariable($k, [string]$vars[$k], 'Machine')  # throws if not admin
    Set-Item -Path "Env:\$k" -Value ([string]$vars[$k])   # this window too, for the test below
}
$NewPassword = $null

# --- 5. One live test ------------------------------------------------------------------------
Step 'Testing: SQL -> MDM (one push)'
$test = & $Python (Join-Path $InstallTo 'leaderboard_collector.py') --once 2>&1 | Out-String
if ($test -notmatch 'pushed:') {
    Write-Host $test
    if ($test -match 'CERTIFICATE_VERIFY_FAILED') {
        Fail 'The server''s security certificate was rejected - the antivirus web protection is intercepting HTTPS. Tell Claude; do not turn verification off.'
    }
    Fail 'The test push did not succeed. Send Claude the text above.'
}
Write-Host ($test.Trim() -split "`n" | Select-Object -Last 2 | Out-String).Trim() -ForegroundColor Green

# --- 6. Background task ----------------------------------------------------------------------
Step 'Registering the background task'
Get-ScheduledTask -TaskName "$TaskName*" -ErrorAction SilentlyContinue | ForEach-Object { Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false -ErrorAction Stop }
$action    = New-ScheduledTaskAction -Execute $PythonW -Argument ('"' + (Join-Path $InstallTo 'leaderboard_collector.py') + '"') -WorkingDirectory $InstallTo
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -MultipleInstances IgnoreNew -Hidden
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -ErrorAction Stop | Out-Null
Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
Start-Sleep -Seconds 20
$state = (Get-ScheduledTask -TaskName $TaskName).State
Write-Host "Task state: $state"
if (Test-Path $LogFile) { Get-Content $LogFile -Tail 3 }

# --- 7. Clean up the staged copy that carries the token --------------------------------------
Step 'Cleaning up'
if ($MyInvocation.MyCommand.Path -like '*\AradhanaDeploy\*') {
    Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
    Write-Host 'Removed the staged installer (it contained the token).'
}
Write-Host ""
Write-Host "DONE. The leaderboard is being pushed every 30 seconds. Log: $LogFile" -ForegroundColor Green
