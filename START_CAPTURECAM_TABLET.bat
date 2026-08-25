@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_capturecam_scrcpy.ps1"
if errorlevel 1 pause
