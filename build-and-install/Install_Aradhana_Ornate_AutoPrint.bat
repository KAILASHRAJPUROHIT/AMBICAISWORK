@echo off
setlocal EnableExtensions
title Install Aradhana Ornate AutoPrint Tray App

set "APPNAME=AradhanaOrnateAutoPrint.exe"
set "BASE=C:\ProgramData\Aradhana\OrnateAutoPrintTray"
set "TARGET=%BASE%\%APPNAME%"
set "SOURCE=%~dp0%APPNAME%"
set "REFERENCE=office-sales-voucher-format-reference.png"
set "REFERENCE_SOURCE=%~dp0%REFERENCE%"
set "REFERENCE_TARGET=%BASE%\%REFERENCE%"
set "RUNKEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
set "RUNNAME=Aradhana Ornate AutoPrint"

net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo ERROR: Right-click this BAT and choose Run as administrator.
  pause
  exit /b 1
)

if not exist "%SOURCE%" (
  echo ERROR: %APPNAME% was not found next to this installer.
  echo Run Build_Aradhana_Ornate_AutoPrint.bat first.
  pause
  exit /b 1
)

if not exist "%BASE%" mkdir "%BASE%"
copy /y "%SOURCE%" "%TARGET%" >nul
if errorlevel 1 (
  echo ERROR: Could not copy the EXE to %BASE%
  pause
  exit /b 1
)

if not exist "%REFERENCE_SOURCE%" (
  echo ERROR: %REFERENCE% was not found next to this installer.
  pause
  exit /b 1
)

copy /y "%REFERENCE_SOURCE%" "%REFERENCE_TARGET%" >nul
if errorlevel 1 (
  echo ERROR: Could not copy the Voucher Format reference to %BASE%
  pause
  exit /b 1
)

reg add "%RUNKEY%" /v "%RUNNAME%" /t REG_SZ /d "\"%TARGET%\"" /f >nul
if errorlevel 1 (
  echo ERROR: Could not create the current-user startup entry.
  pause
  exit /b 1
)

start "" "%TARGET%"

echo.
echo Installed and started.
echo.
echo Location:
echo   %TARGET%
echo.
echo Auto-start:
echo   Current Windows user's HKCU Run entry
echo.
echo No PowerShell Scheduled Task is used.
echo No Windows Service is used.
echo.
echo Look for the tray icon near the clock.
echo Right-click it for Enable/Disable, Open Log, or Exit.
echo.
echo IMPORTANT TEST:
echo 1. Print from Ornate - it should auto-confirm.
echo 2. Keep Ornate open and print from Notepad.
echo    Notepad MUST NOT auto-confirm.
echo.
pause
