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

:: 2. Link Bank Evidence (Foolproof Recon V3)
echo [1.5/2] Linking bank evidence...
py -3.11 -c "from backend.reconciliation.reconciliation_engine_v3 import ReconciliationEngineV3; ReconciliationEngineV3().process_reconciliation('C:/Aradhana/PrimeExports/JSON/prime_report_import.json', 'C:/Aradhana/BankImports/bank_payments_until_yesterday.json')"

:: 3. Launch App
echo [2/2] Launching application...
call start_aradhana_auditor.bat
