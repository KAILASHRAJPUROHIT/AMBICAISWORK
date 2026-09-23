@echo off
setlocal EnableExtensions
title Build Ornate Spool Observer (diagnostic, read-only)

set "HERE=%~dp0"
set "SRC=%HERE%OrnateSpoolObserver.cs"
set "EXE=%HERE%OrnateSpoolObserver.exe"

set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"

if not exist "%CSC%" (
  echo ERROR: .NET Framework C# compiler was not found.
  pause
  exit /b 1
)

echo Building read-only spool observer...
"%CSC%" /nologo /target:exe /optimize+ ^
 /reference:System.dll ^
 /reference:System.Drawing.dll ^
 /out:"%EXE%" "%SRC%"

if errorlevel 1 (
  echo.
  echo BUILD FAILED.
  pause
  exit /b 1
)

echo.
echo Built: %EXE%
echo This is an unsigned, standalone diagnostic tool. Run it manually on PC2
echo (or any machine you want to observe) while real bills print, and let it
echo run for a while to see many copies/voucher/timing combinations. It does
echo not install, auto-start, or touch any print job.
pause
