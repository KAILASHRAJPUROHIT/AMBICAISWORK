@echo off
TITLE Aradhana Payment Auditor Launcher
SETLOCAL EnableDelayedExpansion

echo ====================================================
echo    ARADHANA PAYMENT AUDITOR - ONE-CLICK LAUNCH
echo ====================================================
echo.

:: 1. Dependency Checks
echo [1/3] Verifying dependencies...

where py >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [WARNING] 'py' command not found. Ensure Python 3.11 is installed.
)

where npm >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] 'npm' not found. Please install Node.js before launching.
    pause
    exit /b
)

if not exist "C:\Aradhana\PrimeExports\JSON\prime_report_import.json" (
    echo [WARNING] Latest Prime report JSON not found in C:\Aradhana.
    echo           Dashboard might show empty data until you run an import.
)

:: 2. Launch Backend
echo [2/5] Starting Backend API (Port 8000)...
start "Aradhana Backend" /min cmd /c "py -3.11 backend/review_api.py"

:: 3. Launch PDF Ingestion
echo [3/5] Starting PDF Ingestion Watcher (Z:\Aradhana\InvoicePDFs)...
start "Aradhana PDF Watcher" /min cmd /c "py -3.11 backend/pdf_ingestion.py"

:: 4. Launch SMS Ingestion
echo [4/5] Starting SMS Ingestion Watcher (Polling Android Gateway)...
start "Aradhana SMS Watcher" /min cmd /c "py -3.11 backend/sms_ingestion.py"

:: 5. Launch Frontend
echo [5/5] Starting Frontend UI (Port 5173)...
cd frontend
start "Aradhana Frontend" /min cmd /c "npm run dev"

:: 6. Finalize
echo.
echo Launch sequence complete. 
echo ----------------------------------------------------
echo Backend (HTTPS): https://127.0.0.1:8000/docs
echo Frontend:        http://localhost:5173
echo ----------------------------------------------------
echo.
echo Opening browser in 5 seconds...
timeout /t 5 >nul
start http://localhost:5173

echo.
echo Close the two minimized command windows to stop the application.
echo.
pause
