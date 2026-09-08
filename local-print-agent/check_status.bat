@echo off
SETLOCAL

echo ===================================================
echo Aradhana Print Agent - Status Check
echo ===================================================
echo.

SET "TASK_NAME=Aradhana Print Agent"
SET "LOG_FILE=%~dp0logs\agent.log"

:: 1. Check Scheduled Task
echo [Scheduled Task Status]
schtasks /query /tn "%TASK_NAME%" /FO LIST
if %errorLevel% neq 0 (
    echo The scheduled task does not exist. Please run install_autostart.bat.
)
echo.

:: 2. Check Running Process
echo [Running Background Processes]
tasklist | findstr pythonw.exe
if %errorLevel% neq 0 (
    echo No 'pythonw.exe' process is currently running! The agent might be stopped.
)
echo.

:: 3. Tail Recent Logs
echo [Recent Log Activity]
if exist "%LOG_FILE%" (
    powershell -NoProfile -Command "Get-Content -Path '%LOG_FILE%' -Tail 15"
) else (
    echo No log file found at %LOG_FILE%. 
    echo The agent may not have executed successfully yet.
)

echo.
echo ===================================================
pause
