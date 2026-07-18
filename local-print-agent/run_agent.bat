@echo off
:: AMBIC SmartQR Print Agent - Background Execution Script
:: This script is called by Windows Task Scheduler to run the print agent silently.

:: 1. Change directory to ensure .env is loaded from the correct folder
cd /d "%~dp0"

:: 2. Launch the agent using pythonw.exe so no console window remains open
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo Missing .venv\Scripts\pythonw.exe>> "%~dp0logs\agent-launch-error.log"
  exit /b 1
)
"%~dp0.venv\Scripts\pythonw.exe" agent.py

exit
