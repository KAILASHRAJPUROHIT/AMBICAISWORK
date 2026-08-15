@echo off
REM ---------------------------------------------------------------------
REM Same launcher as LAUNCH_CATALOG_UI.bat, but with the 2026-08-09 output
REM changes switched ON:
REM
REM   * realism clause      - polished gold reflects the softbox instead of
REM                           reading as a flat CGI render
REM   * 4 MP lanczos ref    - was 1 MP nearest-exact, which aliased fine
REM                           detail away before Klein ever saw it
REM   * 2048 output         - was 768 upscaled to a 2400 final
REM
REM These change EVERY image and cost roughly +40-60s each. They have not
REM been compared against the baseline that produced Processed_Old/earrings,
REM so run a batch with this launcher, compare, and decide.
REM
REM The ordinary LAUNCH_CATALOG_UI.bat keeps the shipping baseline.
REM Both launchers always include the topology fix and the crash guards.
REM ---------------------------------------------------------------------
@echo on
set VC_2026_08_09=1
@echo off
echo.
echo   VC_2026_08_09=1  -  realism clause + 4 MP lanczos + 2048 output ENABLED
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_catalog_ui.ps1"
if errorlevel 1 pause
