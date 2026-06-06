@echo off
SETLOCAL
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\aradhana_service_control.ps1" stop-dev
ENDLOCAL
