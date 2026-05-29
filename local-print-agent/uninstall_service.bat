@echo off
SETLOCAL EnableDelayedExpansion

SET "SERVICE_NAME=AradhanaPrintAgent"
SET "NSSM_EXE=%~dp0nssm.exe"

echo ===================================================
echo Aradhana Print Agent - NSSM Service Uninstaller
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

if not exist "%NSSM_EXE%" (
    echo ERROR: nssm.exe not found! Make sure it is in this folder.
    pause
    exit /b 1
)

echo Stopping the %SERVICE_NAME% service...
"%NSSM_EXE%" stop "%SERVICE_NAME%"

echo.
echo Removing the service...
"%NSSM_EXE%" remove "%SERVICE_NAME%" confirm

echo.
echo ===================================================
echo SUCCESS: Service uninstalled!
echo ===================================================
pause
