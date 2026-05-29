@echo off
SETLOCAL

echo ===================================================
echo Aradhana Print Agent - Task Scheduler Uninstaller
echo ===================================================
echo.

:: 1. Check for Administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Administrator privileges required!
    echo Please right-click this script and select "Run as administrator".
    pause
    exit /b 1
)

SET "TASK_NAME=Aradhana Print Agent"

:: 2. Stop running processes
echo Stopping background print agent processes...
taskkill /F /IM pythonw.exe >nul 2>&1
schtasks /end /tn "%TASK_NAME%" >nul 2>&1

:: 3. Delete Scheduled Task
echo Deleting Scheduled Task...
schtasks /delete /tn "%TASK_NAME%" /F

echo.
echo ===================================================
echo SUCCESS: Print Agent autostart has been removed.
echo ===================================================
pause
