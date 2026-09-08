@echo off
SETLOCAL

set "TASK_NAME=AradhanaAuditorProductionAutostart"

echo =====================================================================
echo Aradhana Auditor Production Autostart Uninstallation
echo =====================================================================
echo.
echo This script will remove the scheduled task that automatically
echo starts the production server on user login.
echo.

echo Task to be removed: %TASK_NAME%
echo.

echo Deleting scheduled task...
schtasks /delete /tn "%TASK_NAME%" /f

if %errorlevel% neq 0 (
    echo.
    echo WARNING: The task '%TASK_NAME%' could not be found or an error occurred.
    echo It may have already been removed.
) else (
    echo.
    echo SUCCESS: The autostart task has been removed.
)
echo.

ENDLOCAL
pause
