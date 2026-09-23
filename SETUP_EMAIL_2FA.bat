@echo off
setlocal
cd /d "%~dp0"
start "" /wait pythonw tools\setup_email_2fa_gui.py
