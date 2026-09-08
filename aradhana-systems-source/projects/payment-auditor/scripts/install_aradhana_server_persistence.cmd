@echo off
setlocal EnableExtensions
fltmc >nul 2>&1
if errorlevel 1 (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -Verb RunAs -FilePath '%ComSpec%' -ArgumentList '/c ""%~f0"" elevated'"
  exit /b
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_aradhana_server_persistence.ps1"
if errorlevel 1 pause
endlocal
