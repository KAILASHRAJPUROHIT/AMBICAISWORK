@echo off
SETLOCAL

echo ===================================================
echo Aradhana Print Agent - Service Restart
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

:: 2. Terminate existing processes
echo Stopping currently running print agent...
taskkill /F /IM pythonw.exe >nul 2>&1
schtasks /end /tn "%TASK_NAME%" >nul 2>&1

:: Brief pause to ensure OS releases file locks
timeout /t 2 /nobreak >nul

:: 3. Start task again
echo.
echo Starting the print agent background task...
schtasks /run /tn "%TASK_NAME%"

echo.
echo ===================================================
echo SUCCESS: Print Agent restarted successfully!
echo ===================================================
pause
