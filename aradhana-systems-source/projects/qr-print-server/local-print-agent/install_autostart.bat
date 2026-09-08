@echo off
SETLOCAL EnableDelayedExpansion

echo ===================================================
echo Aradhana Print Agent - Task Scheduler Installer
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

:: 2. Define Paths
SET "AGENT_DIR=%~dp0"
SET "PYTHON_PATH=C:\Users\kaila\AppData\Local\Programs\Python\Python311\pythonw.exe"
SET "TASK_NAME=Aradhana Print Agent"

:: 3. Verification checks
if not exist "%PYTHON_PATH%" (
    echo ERROR: pythonw.exe not found at %PYTHON_PATH%
    echo Please verify your Python installation path.
    pause
    exit /b 1
)

if not exist "%AGENT_DIR%agent.py" (
    echo ERROR: agent.py not found in %AGENT_DIR%
    pause
    exit /b 1
)

if not exist "%AGENT_DIR%.env" (
    echo ERROR: .env file not found in %AGENT_DIR%
    echo Please create the .env file before installing the service.
    pause
    exit /b 1
)

:: 4. Ensure logs folder exists
if not exist "%AGENT_DIR%logs" (
    mkdir "%AGENT_DIR%logs"
    echo Created missing logs directory.
)

:: 5. Create Scheduled Task (Overwrites safely if exists)
echo Installing Scheduled Task...
schtasks /create /tn "%TASK_NAME%" /tr "\"%AGENT_DIR%run_agent.bat\"" /sc onstart /ru SYSTEM /rl HIGHEST /F

:: 6. Start the task immediately
echo.
echo Starting the print agent background task...
schtasks /run /tn "%TASK_NAME%"

echo.
echo ===================================================
echo SUCCESS: Print Agent installed and running!
echo It will now start automatically whenever Windows boots.
echo ===================================================
pause
