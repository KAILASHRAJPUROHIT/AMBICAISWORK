@echo off
SETLOCAL

set "TASK_NAME=AradhanaAuditorProductionAutostart"
set "SCRIPT_FILE_PATH=%~dp0scripts\aradhana_service_control.ps1"
set "WORKING_DIRECTORY=%~dp0"

echo =================================================================
echo Aradhana Auditor Production Autostart Setup
echo =================================================================
echo.

echo This script will create a scheduled task to start the production
echo server automatically when a user logs in.
echo.

rem The command that the scheduled task will run.
rem It executes the main PowerShell control script in a hidden window.
set "COMMAND_TO_RUN=powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%SCRIPT_FILE_PATH%" -Mode start-prod"

echo Task Name: %TASK_NAME%
echo Command:   %COMMAND_TO_RUN%
echo.

echo Creating/updating scheduled task...
schtasks /create /tn "%TASK_NAME%" /tr "%COMMAND_TO_RUN%" /sc ONLOGON /rl HIGHEST /f

rem Check the exit code of schtasks
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to create the scheduled task.
    echo Please run this script as an Administrator.
    goto :eof
)

echo.
echo SUCCESS: The autostart task has been configured.
echo The Aradhana Auditor production server will now start automatically
echo when any user logs into this machine.
echo.
echo To verify the task, open Task Scheduler or run:
echo schtasks /query /tn "%TASK_NAME%"
echo.

ENDLOCAL
pause
