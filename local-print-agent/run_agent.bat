@echo off
:: Aradhana Print Agent - Background Execution Script
:: This script is called by Windows Task Scheduler to run the print agent silently.

:: 1. Change directory to ensure .env is loaded from the correct folder
cd /d "%~dp0"

:: 2. Launch the agent using pythonw.exe so no console window remains open
"C:\Users\kaila\AppData\Local\Programs\Python\Python311\pythonw.exe" agent.py

exit
