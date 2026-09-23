@echo off
REM Stable entry point. PowerShell owns orchestration because cmd.exe parses
REM parentheses inside multiline IF blocks and broke the previous launcher.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_catalog_ui.ps1"
if errorlevel 1 pause
