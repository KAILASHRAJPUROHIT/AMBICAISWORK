@echo off
setlocal EnableExtensions
title Uninstall Aradhana Ornate AutoPrint Tray App

set "BASE=C:\ProgramData\Aradhana\OrnateAutoPrintTray"
set "RUNKEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
set "RUNNAME=Aradhana Ornate AutoPrint"

reg delete "%RUNKEY%" /v "%RUNNAME%" /f >nul 2>&1
taskkill /im AradhanaOrnateAutoPrint.exe /f >nul 2>&1
timeout /t 1 /nobreak >nul
if exist "%BASE%" rmdir /s /q "%BASE%"

echo Uninstalled.
pause
