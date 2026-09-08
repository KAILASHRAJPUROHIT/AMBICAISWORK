@echo off
setlocal EnableExtensions
title Build Aradhana Ornate AutoPrint Tray App v2

set "HERE=%~dp0"
set "SRC=%HERE%..\src\AradhanaOrnateAutoPrint.cs"
set "EXE=%HERE%AradhanaOrnateAutoPrint.exe"

set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"

if not exist "%CSC%" (
  echo ERROR: .NET Framework C# compiler was not found.
  echo Expected csc.exe under %%WINDIR%%\Microsoft.NET\Framework*\v4.0.30319
  pause
  exit /b 1
)

echo Building...
"%CSC%" /nologo /target:winexe /optimize+ ^
 /reference:System.dll ^
 /reference:System.Drawing.dll ^
 /reference:System.Security.dll ^
 /reference:System.Windows.Forms.dll ^
 /out:"%EXE%" "%SRC%"

if errorlevel 1 (
  echo.
  echo BUILD FAILED.
  pause
  exit /b 1
)

echo.
echo BUILD SUCCESS:
echo %EXE%
echo.
echo Now right-click Install_Aradhana_Ornate_AutoPrint.bat
echo and choose Run as administrator.
pause
