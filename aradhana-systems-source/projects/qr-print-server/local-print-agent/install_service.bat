@echo off
SETLOCAL EnableDelayedExpansion

:: Define variables
SET "SERVICE_NAME=AradhanaPrintAgent"
SET "NSSM_EXE=%~dp0nssm.exe"
SET "AGENT_DIR=%~dp0"
SET "PYTHON_EXE=python.exe"

echo ===================================================
echo Aradhana Print Agent - NSSM Service Installer
echo ===================================================
echo.

:: Check for Administrator privileges
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Administrator privileges confirmed.
) else (
    echo ERROR: Administrator privileges required!
    echo Please right-click this script and select "Run as administrator".
    pause
    exit /b 1
)

:: Check if nssm.exe exists in the folder
if not exist "%NSSM_EXE%" (
    echo ERROR: nssm.exe not found!
    echo Please download NSSM from http://nssm.cc/ and extract nssm.exe 
    echo ^(the 64-bit version^) into this folder:
    echo %AGENT_DIR%
    pause
    exit /b 1
)

echo Installing %SERVICE_NAME%...
"%NSSM_EXE%" install "%SERVICE_NAME%" "%PYTHON_EXE%" "agent.py"

echo Configuring service parameters...
:: Set the working directory so .env and logs are found correctly
"%NSSM_EXE%" set "%SERVICE_NAME%" AppDirectory "%AGENT_DIR%\"

:: Ensure it starts automatically with Windows (before login)
"%NSSM_EXE%" set "%SERVICE_NAME%" Start SERVICE_AUTO_START

:: Configure Automatic Restart on Crash
"%NSSM_EXE%" set "%SERVICE_NAME%" AppThrottle 1500
"%NSSM_EXE%" set "%SERVICE_NAME%" AppExit Default Restart
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRestartDelay 5000

:: Redirect standard output and errors (catches Python crash tracebacks)
if not exist "%AGENT_DIR%logs" mkdir "%AGENT_DIR%logs"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStdout "%AGENT_DIR%logs\nssm_stdout.log"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStderr "%AGENT_DIR%logs\nssm_stderr.log"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStdoutCreationDisposition 4
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStderrCreationDisposition 4
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRotateFiles 1
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRotateOnline 1
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRotateBytes 5242880

:: Set description
"%NSSM_EXE%" set "%SERVICE_NAME%" Description "Background daemon for Aradhana Print Server. Polls cloud and prints automatically."

echo.
echo Starting the service...
"%NSSM_EXE%" start "%SERVICE_NAME%"

echo.
echo ===================================================
echo SUCCESS: Service installed and started!
echo ===================================================
pause
