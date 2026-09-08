@echo off
setlocal
set "SETUP=%~dp0scripts\install_bank_activity_always_on.ps1"
if not exist "%SETUP%" (
  echo Missing: %SETUP%
  echo Keep this CMD file in the Aradhana Payment Auditor project root.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""%SETUP%""'"
if errorlevel 1 (
  echo Setup failed or Administrator approval was cancelled.
  pause
  exit /b 1
)
pause
