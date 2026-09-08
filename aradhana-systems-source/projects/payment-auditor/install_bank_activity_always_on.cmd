@echo off
setlocal
set "SCRIPT=%~dp0scripts\install_bank_activity_always_on.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""%SCRIPT%""'"
if errorlevel 1 (
  echo Installation failed or Administrator approval was cancelled.
  pause
  exit /b 1
)
echo Aradhana Bank Activity always-on setup complete.
pause
