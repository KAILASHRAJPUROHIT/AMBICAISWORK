@echo off
TITLE Aradhana Auditor - Import and Launch
SETLOCAL EnableDelayedExpansion

echo ====================================================
echo    ARADHANA AUDITOR - IMPORT DATA AND LAUNCH
echo ====================================================
echo.

:: 1. Import Data
echo [1/2] Importing latest Prime reports...
py -3.11 scripts\prime_report_importer.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Import failed. Check reports in C:\Aradhana\PrimeExports\ManualReports.
    pause
    exit /b
)

echo.
echo [SUCCESS] Import complete.
echo.

:: 2. Launch App
echo [2/2] Launching application...
call start_aradhana_auditor.bat
