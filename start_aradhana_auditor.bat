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
echo [2/3] Starting Backend API (Port 8000)...
echo       NOTE: DO NOT USE backend.main:app for live dashboard.
echo       Launching: backend.review_api:app
start "Aradhana Backend" /min cmd /c "py -3.11 -m uvicorn backend.review_api:app --reload --host 127.0.0.1 --port 8000"

:: 3. Launch Frontend
echo [3/3] Starting Frontend UI (Port 5173)...
cd frontend
start "Aradhana Frontend" /min cmd /c "npm run dev"

:: 4. Finalize
echo.
echo Launch sequence complete. 
echo ----------------------------------------------------
echo Backend:  http://127.0.0.1:8000/docs
echo Frontend: http://localhost:5173
echo ----------------------------------------------------
echo.
echo Opening browser in 5 seconds...
timeout /t 5 >nul
start http://localhost:5173

echo.
echo Close the two minimized command windows to stop the application.
echo.
pause
