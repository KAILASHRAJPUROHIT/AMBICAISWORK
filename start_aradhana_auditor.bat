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

:: Set PYTHONPATH to ensure backend imports resolve correctly
set PYTHONPATH=.

:: 2. Launch Backend
echo [2/3] Starting Backend API (Port 8000)...
start "Aradhana Backend" /min cmd /c "py -3.11 backend/review_api.py"

echo Waiting for backend to become healthy...
set max_retries=30
set retry_count=0

:check_backend
:: Check HTTP first
curl -s -k -f http://127.0.0.1:8000/health > nul 2>&1
if %ERRORLEVEL% equ 0 goto backend_ready
:: Fallback to HTTPS check
curl -s -k -f https://127.0.0.1:8000/health > nul 2>&1
if %ERRORLEVEL% equ 0 goto backend_ready

set /a retry_count+=1
if %retry_count% geq %max_retries% (
    echo [ERROR] Backend failed to start or become healthy after 30 seconds.
    echo Please check backend console for errors.
    pause
    exit /b 1
)
timeout /t 1 > nul
goto check_backend

:backend_ready
echo Backend is healthy.

:: 3. Launch Frontend
echo [3/3] Starting Frontend UI (Port 5173)...
cd frontend
start "Aradhana Frontend" /min cmd /c "npm run dev"
cd ..

echo Waiting for frontend to become available...
set max_retries_fe=30
set retry_count_fe=0

:check_frontend
curl -s -f http://localhost:5173 > nul 2>&1
if %ERRORLEVEL% equ 0 goto frontend_ready

set /a retry_count_fe+=1
if %retry_count_fe% geq %max_retries_fe% (
    echo [ERROR] Frontend failed to start after 30 seconds.
    echo Please check frontend console for errors.
    pause
    exit /b 1
)
timeout /t 1 > nul
goto check_frontend

:frontend_ready
echo Frontend is ready.

:: 4. Finalize
echo.
echo Launch sequence complete. 
echo ----------------------------------------------------
echo Backend:  http://127.0.0.1:8000/docs or https://127.0.0.1:8000/docs
echo Frontend: http://localhost:5173
echo ----------------------------------------------------
echo.
echo Opening browser...
start http://localhost:5173

echo.
echo Close the two minimized command windows to stop the application.
echo.
pause
