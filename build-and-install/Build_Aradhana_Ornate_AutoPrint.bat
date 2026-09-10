@echo off
setlocal EnableExtensions
title Build Aradhana Ornate AutoPrint Tray App v2

set "HERE=%~dp0"
set "SRC=%HERE%..\src\AradhanaOrnateAutoPrint.cs"
set "EXE=%HERE%AradhanaOrnateAutoPrint.exe"
set "REFERENCE_SOURCE=%HERE%..\assets\office-sales-voucher-format-reference.png"
set "REFERENCE_TARGET=%HERE%office-sales-voucher-format-reference.png"

set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
set "SIGNTOOL=%ProgramFiles(x86)%\Windows Kits\10\App Certification Kit\signtool.exe"
if not exist "%SIGNTOOL%" set "SIGNTOOL=%ProgramFiles(x86)%\Windows Kits\10\bin\10.0.19041.0\x64\signtool.exe"
set "CERT_THUMBPRINT=E3880C0CAAE350308C78CB0646260C13A35438E2"

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

if not exist "%REFERENCE_SOURCE%" (
  echo ERROR: Approved Voucher Format reference is missing: %REFERENCE_SOURCE%
  pause
  exit /b 1
)
copy /y "%REFERENCE_SOURCE%" "%REFERENCE_TARGET%" >nul
if errorlevel 1 (
  echo ERROR: Could not stage the approved Voucher Format reference.
  pause
  exit /b 1
)

if not exist "%SIGNTOOL%" (
  echo ERROR: signtool.exe was not found. Refusing to create an unsigned production router EXE.
  pause
  exit /b 1
)

echo Signing with the approved Aradhana internal certificate...
"%SIGNTOOL%" sign /sha1 %CERT_THUMBPRINT% /fd SHA256 "%EXE%"
if errorlevel 1 (
  echo ERROR: Code signing failed. Refusing to release an unsigned EXE.
  pause
  exit /b 1
)

powershell -NoProfile -Command "$s=Get-AuthenticodeSignature -FilePath '%EXE%'; if($s.Status -ne 'Valid'){Write-Error ('Signature status: ' + $s.Status); exit 1}"
if errorlevel 1 (
  echo ERROR: Signature verification failed. Refusing to release this EXE.
  pause
  exit /b 1
)

echo.
echo BUILD SUCCESS:
echo %EXE%
echo Signed and verified with SHA-256 Authenticode.
echo.
echo Now right-click Install_Aradhana_Ornate_AutoPrint.bat
echo and choose Run as administrator.
pause
