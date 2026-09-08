@echo off
setlocal
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js 20 or newer is required.
  echo Install Node.js, then run this file again.
  pause
  exit /b 1
)
if not exist node_modules\whatsapp-web.js\package.json (
  echo Installing dependencies for first run...
  set "PUPPETEER_SKIP_DOWNLOAD=true"
  call npm install
  if errorlevel 1 pause & exit /b 1
)
echo.
echo Starting Aradhana Counter Form...
echo First WhatsApp login will show a QR code in this window.
echo Scan it ONLY from +91 89561 43245.
echo.
call npm start
pause
